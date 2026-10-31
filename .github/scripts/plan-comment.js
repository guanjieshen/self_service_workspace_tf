// Builds and posts the plan comment for one workspace on a pull request.
// Used by .github/workflows/deploy.yml through actions/github-script.
//
// Reads the files scripts/tf.sh and the plan workflow write to .plans/:
//   <ws>.txt         full plan            <ws>.changes     number of changes
//   <ws>.guard.txt   plan guard output    <ws>.guard  its status (0 = nothing flagged)  <ws>.summary.md  tf-summarize table
//   <ws>.preflight.txt  problems scripts/preflight.py found
//   <ws>.ai.md       AI impact review
const fs = require('fs');

// GitHub comments are limited to 65,536 characters; the full plan gets what is left.
const MAX_COMMENT = 64000;

function marker(ws) {
  return `<!-- plan:${ws} -->`;
}

// Values that must never be posted: JSON web tokens, and token=, secret= or password= values.
// A failed sign-in (preflight, or the Terraform provider) can print its configuration,
// including the GitHub OIDC request token; logs mask it, comments and issues do not.
function redact(text) {
  return String(text)
    .replace(/eyJ[\w-]+\.[\w-]+\.[\w-]+/g, '***')
    .replace(/\b([\w-]*(?:token|secret|password)[\w-]*)=[^,\s]+/gi, '$1=***');
}

// One comment, written to be read in about 30 seconds: what the AI review says the change
// means, then what must happen before merging (decided only by the plan guard, never by
// the AI), then the evidence, collapsed. Without an AI review the guard's status stands alone.
function buildBody(ws, endpoint, dir = '.plans') {
  const read = (name) => {
    const f = `${dir}/${ws}${name}`;
    return fs.existsSync(f) ? redact(fs.readFileSync(f, 'utf8')) : '';
  };
  const plan = read('.txt');
  const guard = read('.guard.txt').trim();
  // Guard output with status 0 is only releases or notes; anything else (or no status) needs approval.
  const flagged = Boolean(guard) && read('.guard').trim() !== '0';
  const changes = read('.changes').trim() || '?';
  const summary = read('.summary.md').trim();
  const ai = read('.ai.md').trim();
  const preflight = read('.preflight.txt').trim();
  // The guard's own count: its output also lists releases and notes, which need no approval.
  const findings = Number((guard.match(/^Needs approval: (\d+) change/m) || [])[1] || 0);

  const sections = [
    marker(ws),
    `### Plan: \`${ws}\` (${changes} resource change${changes === '1' ? '' : 's'})`,
    preflight ? (/^error:/m.test(preflight)
      ? '> [!CAUTION]\n> Preflight found problems with this workspace (`scripts/preflight.py`). Errors stop the plan; fix them first.'
      : '> [!NOTE]\n> Preflight warnings for this workspace (`scripts/preflight.py`). They do not stop the plan.') + '\n\n```\n' + preflight + '\n```' : '',
    ai,
    flagged ? '### Before merging\n\n' +
      `The plan guard flagged ${findings || 'some'} change${findings === 1 ? '' : 's'} that ${findings === 1 ? 'is' : 'are'} hard to undo or weaken${findings === 1 ? 's' : ''} security, so this needs explicit approval. ` +
      'If a person has reviewed it and approves, add the `allow-risky-changes` label; otherwise change the configuration. ' +
      'The label records the approval; it does not make the change safer.' : '',
  ];
  // Each part is capped, so the comment always fits: a plan touching hundreds of resources
  // makes a long guard list and summary table, and GitHub rejects a comment over the limit.
  const cap = (text, max) => (text.length > max ? text.slice(0, max) + '\n... (cut; see the job log)' : text);
  const details = [
    guard ? '**Plan guard**\n\n```\n' + cap(guard, 15000) + '\n```' : '',
    summary ? '**Changed resources**\n\n' + cap(summary, 15000) : '',
  ].filter(Boolean);
  const footer = ai ? `<sub>*AI-generated review (\`${endpoint}\`) based on the Terraform plan. Verify findings before merging.*</sub>` : '';
  const room = Math.max(0, MAX_COMMENT - sections.join('\n\n').length - details.join('\n\n').length - footer.length - 400);
  details.push(plan
    ? '**Full Terraform plan**\n\n```\n' + (plan.length > room ? '... (start of plan cut; see the job log)\n' + plan.slice(-room) : plan) + '\n```'
    : '_Plan failed; see the job log._');
  sections.push('<details><summary>Technical details</summary>\n\n' + details.join('\n\n') + '\n\n</details>', footer);
  return sections.filter(Boolean).join('\n\n');
}

// Whether a workspace's plan is worth a comment: it changes something, failed, or preflight
// found an error. A workspace a change does not touch plans no changes and gets none.
function worthPosting(ws, dir = '.plans') {
  const read = (name) => {
    const f = `${dir}/${ws}${name}`;
    return fs.existsSync(f) ? fs.readFileSync(f, 'utf8').trim() : '';
  };
  // Preflight warnings alone repeat on every pull request: they are shown with a plan that
  // changes something, and in the job's annotations.
  return read('.changes') !== '0' || /^error:/m.test(read('.preflight.txt'));
}

// What merging a pull request that deletes a workspace's file does. Retirement plans
// nothing (Terraform only forgets the workspace), so this comment stands in for the plan.
function retireBody(ws) {
  return [
    marker(ws),
    `### Retire: \`${ws}\``,
    `This pull request deletes \`config/workspaces/${ws}.yaml\`. When it is merged, the workspace's Terraform state is deleted and this repository stops managing it.`,
    '**Nothing in the workspace changes:** its settings, groups, catalog and data stay as they are, and nobody keeps them at the baseline any more. ' +
      'Deleting the workspace itself is a separate decision, outside this repository.',
    'Retired by mistake? Restore the state file from the storage account\'s blob versions, then restore the workspace file (docs/SETUP.md, troubleshooting).',
  ].join('\n\n');
}

// Creates the workspace's comment, or updates it on later pushes. An existing comment is
// updated even when there is nothing to show any more, so it never goes stale.
async function upsert({ github, context }, ws, body, create) {
  const { owner, repo } = context.repo;
  const issue_number = context.issue.number;
  const comments = await github.paginate(github.rest.issues.listComments, { owner, repo, issue_number });
  const mine = comments.find((c) => c.body.startsWith(marker(ws)));
  if (mine) await github.rest.issues.updateComment({ owner, repo, comment_id: mine.id, body });
  else if (create) await github.rest.issues.createComment({ owner, repo, issue_number, body });
}

async function post(ctx, ws, endpoint, dir = '.plans') {
  await upsert(ctx, ws, buildBody(ws, endpoint, dir), worthPosting(ws, dir));
}

async function postRetire(ctx, ws) {
  await upsert(ctx, ws, retireBody(ws), true);
}

module.exports = { buildBody, retireBody, post, postRetire, worthPosting, redact };
