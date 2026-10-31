// .github/scripts/plan-comment.js: the plan comment for each workspace.
//   node --test .github/scripts/tests/
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { buildBody, retireBody, post, postRetire } = require('../plan-comment.js');

function plans(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plans-'));
  for (const [name, text] of Object.entries(files)) fs.writeFileSync(path.join(dir, `ws${name}`), text);
  return dir;
}

test('a full comment has every section, in order', () => {
  const body = buildBody('ws', 'system.ai.model', plans({
    '.txt': 'Plan: 1 to add', '.changes': '1', '.guard.txt': 'Needs approval: 1 change\n  - DELETE folder\n      module.x', '.guard': '2\n',
    '.ai.md': '**🔴 High risk: a folder is deleted**', '.summary.md': '| table |',
  }));
  assert.ok(body.startsWith('<!-- plan:ws -->'), 'starts with the marker used to find and update it');
  assert.match(body, /### Plan: `ws` \(1 resource change\)/);
  const order = ['High risk', '### Before merging', '<summary>Technical details</summary>', '**Plan guard**', '**Changed resources**', '**Full Terraform plan**', 'AI-generated review'].map((x) => body.indexOf(x));
  assert.ok(order.every((i, n) => i > 0 && (n === 0 || i > order[n - 1])), `sections in order: ${order}`);
  assert.match(body, /AI-generated review \(`system.ai.model`\) based on the Terraform plan\. Verify findings before merging\./);
  assert.ok(!body.includes('!!!!'), 'no ASCII banner');
});

test('optional sections are left out', () => {
  const body = buildBody('ws', 'm', plans({ '.txt': 'No changes.', '.changes': '0' }));
  assert.match(body, /\(0 resource changes\)/);
  for (const s of ['Before merging', 'AI-generated', 'Changed resources']) assert.ok(!body.includes(s), s);
  assert.ok(body.includes('Full Terraform plan'));
});

test('approval is asked for only when the plan guard flagged something', () => {
  const flagged = buildBody('ws', 'm', plans({ '.txt': 'p', '.guard.txt': 'Left unmanaged from now on:\n  - RELEASE r\n\nNeeds approval: 2 changes that are hard to undo\n  - LOOSEN x\n  - DELETE y', '.guard': '2\n' }));
  assert.match(flagged, /### Before merging[^]*flagged 2 changes[^]*`allow-risky-changes`[^]*does not make the change safer/);
  const noted = buildBody('ws', 'm', plans({ '.txt': 'p', '.guard.txt': 'Not flagged, with the evidence: DISABLE legacy access', '.guard': '0\n' }));
  assert.ok(!noted.includes('Before merging') && !noted.includes('allow-risky-changes'), 'no approval asked when the guard needs none');
  assert.ok(/<details><summary>Technical details[^]*DISABLE legacy access/.test(noted), 'what the guard noted stays in the technical details');
  assert.match(buildBody('ws', 'm', plans({ '.txt': 'p', '.guard.txt': '  - DELETE folder' })), /### Before merging/, 'no status: approval asked, to be safe');
  assert.ok(!buildBody('ws', 'm', plans({ '.txt': 'p' })).includes('AI-generated'), 'no AI footer without an AI review');
});

test('a failed plan says so', () => {
  assert.match(buildBody('ws', 'm', plans({})), /_Plan failed; see the job log._/);
});

test('preflight problems are shown before the plan', () => {
  const body = buildBody('ws', 'm', plans({ '.preflight.txt': 'error: group fin_builder (builder) does not exist in the account\n' }));
  assert.match(body, /Preflight found problems/);
  assert.ok(body.includes('fin_builder') && body.includes('_Plan failed; see the job log._'));
  assert.doesNotMatch(buildBody('ws', 'm', plans({ '.preflight.txt': '' })), /Preflight/);
});

test('a workspace with no changes gets no new comment, but an existing one is updated', async () => {
  const { post, worthPosting } = require('../plan-comment.js');
  const quiet = plans({ '.changes': '0', '.txt': 'No changes.' });
  assert.equal(worthPosting('ws', quiet), false);
  assert.equal(worthPosting('ws', plans({ '.changes': '0', '.preflight.txt': 'error: x' })), true, 'preflight problems are shown');
  assert.equal(worthPosting('ws', plans({ '.changes': '0', '.preflight.txt': 'warning: placeholder' })), false, 'warnings alone do not post a new comment');
  assert.equal(worthPosting('ws', plans({ '.changes': '3' })), true);
  assert.equal(worthPosting('ws', plans({})), true, 'a failed plan is shown');
  const calls = [];
  let existing = [];
  const github = {
    paginate: async () => existing,
    rest: { issues: { listComments: 'list', createComment: async () => calls.push('create'), updateComment: async () => calls.push('update') } },
  };
  const context = { repo: { owner: 'o', repo: 'r' }, issue: { number: 1 } };
  await post({ github, context }, 'ws', 'm', quiet);
  assert.deepEqual(calls, [], 'nothing posted for a plan with no changes');
  existing = [{ id: 9, body: '<!-- plan:ws -->\nold' }];
  await post({ github, context }, 'ws', 'm', quiet);
  assert.deepEqual(calls, ['update'], 'an earlier comment is brought up to date');
});

test('credentials are never posted: tokens and token= values are redacted in every section', () => {
  const leak = 'cannot sign in to https://adb-1.1.azuredatabricks.net: failed during request visitor: github-oidc-azure auth: not configured. Config: host=https://adb-1.1.azuredatabricks.net, account_id=acct, actions_id_token_request_url=https://x/idtoken?api-version=2.0, actions_id_token_request_token=eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJyZXBvIn0.c2lnbmF0dXJl. Env: DATABRICKS_HOST';
  const body = buildBody('ws', 'm', plans({ '.preflight.txt': 'error: ' + leak, '.txt': 'Error: ' + leak, '.changes': '1' }));
  assert.ok(!body.includes('eyJhbGci'), 'no JSON web token');
  assert.ok(!body.includes('c2lnbmF0dXJl'), 'no part of it');
  assert.match(body, /actions_id_token_request_token=\*\*\*/);
  assert.match(body, /cannot sign in to https:\/\/adb-1\.1\.azuredatabricks\.net/, 'the useful part stays');
  const { redact } = require('../plan-comment.js');
  assert.equal(redact('client_secret=abc password=x, plain'), 'client_secret=*** password=***, plain');
});

test('preflight warnings alone are a note, not a stop', () => {
  const body = buildBody('ws', 'm', plans({ '.preflight.txt': 'warning: placeholder left\n', '.txt': 'Plan: 1 to add', '.changes': '1' }));
  assert.match(body, /\[!NOTE\]/);
  assert.doesNotMatch(body, /Errors stop the plan/);
});

test('a long plan is cut from the start to fit in a GitHub comment', () => {
  const plan = 'start\n' + 'x'.repeat(200000) + '\nend of plan';
  const body = buildBody('ws', 'm', plans({ '.txt': plan, '.changes': '9', '.ai.md': 'review' }));
  assert.ok(body.length <= 65536, `length ${body.length}`);
  assert.ok(body.includes('end of plan') && !body.includes('start\n'), 'keeps the end of the plan');
  assert.ok(body.includes('review'), 'keeps the review');
});

test('post updates the workspace comment, or creates it', async () => {
  const calls = [];
  const github = {
    paginate: async () => [{ id: 7, body: '<!-- plan:other -->' }, { id: 8, body: '<!-- plan:ws -->\nold' }],
    rest: { issues: {
      listComments: {},
      updateComment: async (a) => calls.push(['update', a.comment_id]),
      createComment: async () => calls.push(['create']),
    } },
  };
  const context = { repo: { owner: 'o', repo: 'r' }, issue: { number: 1 } };
  const cwd = process.cwd();
  process.chdir(path.dirname(plans({})));
  try {
    await post({ github, context }, 'ws', 'm');
    github.paginate = async () => [];
    await post({ github, context }, 'ws', 'm');
  } finally {
    process.chdir(cwd);
  }
  assert.deepStrictEqual(calls, [['update', 8], ['create']]);
});

test('a retirement says what merging does, and is always posted', async () => {
  const body = retireBody('hr');
  assert.ok(body.startsWith('<!-- plan:hr -->'), 'the same marker as the plan, so it replaces an older plan comment');
  assert.ok(body.includes('config/workspaces/hr.yaml') && /Nothing in the workspace changes/.test(body));
  const calls = [];
  const github = {
    paginate: async () => [],
    rest: { issues: { listComments: {}, updateComment: async () => calls.push('update'), createComment: async (a) => calls.push(a.body) } },
  };
  await postRetire({ github, context: { repo: { owner: 'o', repo: 'r' }, issue: { number: 1 } } }, 'hr');
  assert.deepStrictEqual(calls, [body]);
});

test('a plan touching hundreds of resources still fits in one GitHub comment', () => {
  const many = (line, n) => Array.from({ length: n }, (_, i) => `${line} ${i}`).join('\n');
  const body = buildBody('ws', 'm', plans({
    '.txt': many('  # module.x will be destroyed', 4000), '.changes': '4000', '.guard': '2\n',
    '.guard.txt': 'Needs approval: 4000 changes\n' + many('  - DELETE permissions\n      module.compute.databricks_permissions.x', 4000),
    '.summary.md': many('| delete | `module.compute.databricks_permissions.x` |', 4000),
  }));
  assert.ok(body.length <= 65536, `${body.length} characters`);
  assert.ok(body.includes('(cut; see the job log)'));
});
