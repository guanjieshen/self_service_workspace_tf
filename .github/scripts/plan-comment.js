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
  const findings = (guard.match(/^  - /gm) || []).length;

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
  const details = [
    guard ? '**Plan guard**\n\n```\n' + guard + '\n```' : '',
    summary ? '**Changed resources**\n\n' + summary : '',
  ].filter(Boolean);
  const footer = ai ? `<sub>*AI-generated review (\`${endpoint}\`) based on the Terraform plan. Verify findings before merging.*</sub>` : '';
  const room = MAX_COMMENT - sections.join('\n\n').length - details.join('\n\n').length - footer.length - 400;
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
  // Preflight warnings alone (a placeholder still in the baseline, ...) repeat on every pull
  // request: they are shown with a plan that changes something, and in the job's annotations.
  return read('.changes') !== '0' || /^error:/m.test(read('.preflight.txt'));
}

// Creates the workspace's comment, or updates it on later pushes (an existing comment is
// updated even when there is nothing to show any more, so it never goes stale).
async function post({ github, context }, ws, endpoint, dir = '.plans') {
  const body = buildBody(ws, endpoint, dir);
  const { owner, repo } = context.repo;
  const issue_number = context.issue.number;
  const comments = await github.paginate(github.rest.issues.listComments, { owner, repo, issue_number });
  const mine = comments.find((c) => c.body.startsWith(marker(ws)));
  if (mine) await github.rest.issues.updateComment({ owner, repo, comment_id: mine.id, body });
  else if (worthPosting(ws, dir)) await github.rest.issues.createComment({ owner, repo, issue_number, body });
}

module.exports = { buildBody, post, worthPosting, redact };
