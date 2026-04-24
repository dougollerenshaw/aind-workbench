# SciComp Roadmap Automation — Sandbox Setup Guide

This guide walks through setting up a fully self-contained personal sandbox to
prototype and demo the three-workflow automation system before deploying to the
AIND org. Claude Code can handle most GitHub API steps automatically; manual
steps and "try it out" checkpoints are explicitly marked.

---

## Overview of what we're building

Three workflows that chain together:

```
[Board-centric teams, e.g. Arielle]
Engineer sets "Project Milestones" field on project board
  → assign-milestone-from-board.yml fires
      → GitHub milestone assigned to issue
          → link-issues-by-milestone.yml fires
              → sub-issue created on roadmap item

[Repo-centric teams, e.g. Dan]
Engineer assigns milestone to issue directly
  → link-issues-by-milestone.yml fires
      → sub-issue created on roadmap item

[You, creating a new roadmap item]
Create Goal issue in scicomp-roadmap-sandbox with repo: lines
  → create-milestones.yml fires
      → milestones created in downstream repos with roadmap URL in description
```

---

## Phase 1: Manual setup (do this yourself in GitHub UI)

### Step 1.1 — Create two private repos

> **MANUAL STEP**: Go to github.com/new and create these two repos.
> Set both to **Private**.

- `dougollerenshaw/scicomp-roadmap-sandbox`
  - This mimics `aind-scientific-computing`
  - Description: "Sandbox for prototyping SciComp roadmap automation"

- `dougollerenshaw/work-repo-sandbox`
  - This mimics any downstream repo like `aind-data-schema`
  - Description: "Sandbox downstream work repo for automation testing"

Initialize both with a README so they're not empty.

---

### Step 1.2 — Create a personal access token

> **MANUAL STEP**: Go to github.com/settings/tokens/new
> 
> - Token name: `scicomp-sandbox-token`
> - Expiration: 90 days (or no expiration for a sandbox)
> - Scopes needed: `repo` (full), `project` (read:project + project)
> - Click Generate token and **copy it** — you won't see it again

---

### Step 1.3 — Add the token as a secret in both repos

> **MANUAL STEP**: Do this for **both** repos:
> 
> Repo → Settings → Secrets and variables → Actions → New repository secret
> - Name: `SERVICE_TOKEN`
> - Value: paste your token from Step 1.2

---

### Step 1.4 — Create a personal GitHub project board

> **MANUAL STEP**: Go to github.com/new?owner=dougollerenshaw (or from your
> profile → Projects → New project)
> 
> - Template: Board or Table (either works)
> - Name: `Work Repo Sandbox Board`
> - Set to **Private**
> 
> Then link it to `work-repo-sandbox`:
> In the project settings, add `dougollerenshaw/work-repo-sandbox` as a
> linked repository.

---

### Step 1.5 — Add a "Project Milestones" field to the board

> **MANUAL STEP**: In your new project board:
> 
> Settings (⚙) → Custom fields → Add field
> - Field name: `Project Milestones`
> - Field type: Single select
> 
> Add two options (you'll fill in real URLs in Phase 3):
> - Option 1 name: `Test Roadmap Goal A`
> - Option 2 name: `Test Roadmap Goal B`
> 
> Leave the descriptions blank for now — you'll add URLs after creating
> the roadmap issues in Phase 3.

---

## Phase 2: Add workflow files (Claude Code can do this)

Ask Claude Code to push the following three files to their respective repos.
Note: these require `workflow` scope on the token, so Claude Code must use
its own GitHub credentials, not yours.

---

### File 1: `create-milestones.yml` → `scicomp-roadmap-sandbox`

Path: `.github/workflows/create-milestones.yml`

```yaml
name: Create milestone in linked repos

on:
  issues:
    types: [opened]

jobs:
  create-milestones:
    runs-on: ubuntu-latest
    steps:
      - name: Parse body and create milestones
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.SERVICE_TOKEN }}
          script: |
            const body = context.payload.issue.body || "";
            const title = context.payload.issue.title;
            const url = context.payload.issue.html_url;
            const owner = "dougollerenshaw";

            const repos = body
              .split("\n")
              .map(line => {
                const match = line.trim().match(/^repo:\s*(.+)$/i);
                return match ? match[1].trim() : null;
              })
              .filter(Boolean);

            if (repos.length === 0) {
              console.log("No repo: entries found in issue body.");
              return;
            }

            for (const repo of repos) {
              try {
                await github.rest.issues.createMilestone({
                  owner,
                  repo,
                  title,
                  description: url
                });
                console.log(`Created milestone "${title}" in ${owner}/${repo}`);
              } catch (err) {
                if (err.status === 422) {
                  console.log(`Milestone already exists in ${owner}/${repo}, skipping.`);
                } else {
                  throw err;
                }
              }
            }
```

---

### File 2: `link-issues-by-milestone.yml` → `work-repo-sandbox`

Path: `.github/workflows/link-issues-by-milestone.yml`

```yaml
name: Link issue to cross-repo milestone parent

on:
  issues:
    types: [milestoned]

jobs:
  link:
    runs-on: ubuntu-latest
    steps:
      - name: Link to parent issue in scicomp-roadmap-sandbox
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.SERVICE_TOKEN }}
          script: |
            const issue = context.payload.issue;
            const milestone = issue.milestone;

            if (!milestone) return;

            const targetOwner = "dougollerenshaw";
            const targetRepo = "scicomp-roadmap-sandbox";

            const url = milestone.description;
            const match = url?.match(/\/issues\/(\d+)$/);

            if (!match) {
              console.log(`Milestone description is not a roadmap URL: ${url}`);
              return;
            }

            const parentNumber = parseInt(match[1]);

            const { data: parent } = await github.rest.issues.get({
              owner: targetOwner,
              repo: targetRepo,
              issue_number: parentNumber
            });

            if (!parent) {
              console.log(`No issue found at ${url}`);
              return;
            }

            await github.request("POST /repos/{owner}/{repo}/issues/{issue_number}/sub_issues", {
              owner: targetOwner,
              repo: targetRepo,
              issue_number: parentNumber,
              sub_issue_id: issue.id,
              headers: {
                "X-GitHub-Api-Version": "2022-11-28"
              }
            });

            console.log(`Linked issue #${issue.number} as sub-issue of ${targetRepo}#${parentNumber}`);
```

---

### File 3: `assign-milestone-from-board.yml` → `work-repo-sandbox`

Path: `.github/workflows/assign-milestone-from-board.yml`

This is the new workflow that bridges Arielle-style board-centric teams with
Dan's milestone-based linking. It fires when someone sets the "Project
Milestones" field on the board, finds or creates the corresponding GitHub
milestone (with the roadmap URL in its description), and assigns it to the
issue — which then triggers `link-issues-by-milestone.yml` automatically.

```yaml
name: Assign milestone from project board field

on:
  projects_v2_item:
    types: [edited]

jobs:
  assign-milestone:
    runs-on: ubuntu-latest
    steps:
      - name: Assign GitHub milestone based on Project Milestones field
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.SERVICE_TOKEN }}
          script: |
            const changes = context.payload.changes;
            const item = context.payload.projects_v2_item;

            // Only act on field_value changes
            if (!changes?.field_value) return;

            // We need to fetch the full project item via GraphQL to get
            // the field name and value
            const projectItemId = item.node_id;

            const query = `
              query($nodeId: ID!) {
                node(id: $nodeId) {
                  ... on ProjectV2Item {
                    content {
                      ... on Issue {
                        id
                        number
                        repository {
                          name
                          owner { login }
                        }
                      }
                    }
                    fieldValues(first: 20) {
                      nodes {
                        ... on ProjectV2ItemFieldSingleSelectValue {
                          name
                          description
                          field { ... on ProjectV2SingleSelectField { name } }
                        }
                      }
                    }
                  }
                }
              }
            `;

            const result = await github.graphql(query, { nodeId: projectItemId });
            const node = result.node;

            if (!node?.content?.number) return;

            const issue = node.content;
            const repoName = issue.repository.name;
            const repoOwner = issue.repository.owner.login;
            const issueNumber = issue.number;

            // Find the Project Milestones field value
            const milestoneField = node.fieldValues.nodes.find(
              f => f.field?.name === "Project Milestones"
            );

            if (!milestoneField) {
              console.log("No Project Milestones field found on this item.");
              return;
            }

            const milestoneName = milestoneField.name;
            const milestoneUrl = milestoneField.description;

            if (!milestoneUrl?.match(/\/issues\/\d+$/)) {
              console.log(`Project Milestone option "${milestoneName}" has no valid roadmap URL in its description.`);
              return;
            }

            console.log(`Setting milestone "${milestoneName}" on ${repoOwner}/${repoName}#${issueNumber}`);

            // Find or create the milestone in the issue's repo
            let milestoneNumber;
            const { data: milestones } = await github.rest.issues.listMilestones({
              owner: repoOwner,
              repo: repoName,
              state: "open"
            });

            const existing = milestones.find(m => m.description === milestoneUrl);
            if (existing) {
              milestoneNumber = existing.number;
              console.log(`Found existing milestone #${milestoneNumber}`);
            } else {
              const { data: created } = await github.rest.issues.createMilestone({
                owner: repoOwner,
                repo: repoName,
                title: milestoneName,
                description: milestoneUrl
              });
              milestoneNumber = created.number;
              console.log(`Created new milestone #${milestoneNumber}`);
            }

            // Assign the milestone to the issue
            await github.rest.issues.update({
              owner: repoOwner,
              repo: repoName,
              issue_number: issueNumber,
              milestone: milestoneNumber
            });

            console.log(`Assigned milestone #${milestoneNumber} to issue #${issueNumber}`);
```

> **NOTE for Claude Code**: workflow files require `workflow` scope to push
> via the API. If blocked, provide the file contents to Doug so he can
> commit them manually via the GitHub UI.

---

## Phase 3: Create test content (mix of manual and automated)

### Step 3.1 — Create two roadmap Goal issues in `scicomp-roadmap-sandbox`

> **Claude Code can do this** using the GitHub API.

Create two issues:

**Issue A:**
- Title: `Test Roadmap Goal A`
- Body:
  ```
  ### Detailed Description
  This is a test roadmap goal to validate the milestone automation.

  repo: work-repo-sandbox
  ```

**Issue B:**
- Title: `Test Roadmap Goal B`
- Body:
  ```
  ### Detailed Description
  A second test roadmap goal.

  repo: work-repo-sandbox
  ```

> **TRY IT OUT**: After creating each issue, go to
> `github.com/dougollerenshaw/work-repo-sandbox/milestones`
> and confirm that milestones named "Test Roadmap Goal A" and
> "Test Roadmap Goal B" were automatically created there, each with a
> roadmap issue URL in the description field.
>
> This confirms `create-milestones.yml` is working.

---

### Step 3.2 — Update the project board field options with URLs

> **MANUAL STEP**: Now that the roadmap issues exist and have URLs, go back
> to your project board settings and update the "Project Milestones" field
> options:
>
> - `Test Roadmap Goal A` description → paste the URL of Issue A
>   (e.g. `https://github.com/dougollerenshaw/scicomp-roadmap-sandbox/issues/1`)
> - `Test Roadmap Goal B` description → paste the URL of Issue B
>
> This is the one-time setup step that connects the board field options to
> real roadmap issues. In production, Arielle would do this when she creates
> a new milestone option on her board.

---

### Step 3.3 — Create test work issues in `work-repo-sandbox`

> **Claude Code can do this** using the GitHub API.

Create three issues:
- `Test work ticket 1` (body: "Some work under Goal A")
- `Test work ticket 2` (body: "More work under Goal A")
- `Test work ticket 3` (body: "Work under Goal B")

Then add all three to the project board:
> **MANUAL STEP**: In your project board, click "+ Add item" and add all
> three issues from `work-repo-sandbox`.

---

## Phase 4: Try out the two linking paths

### Path A — Dan's way (direct milestone assignment)

> **MANUAL STEP**: Go to `Test work ticket 1` in `work-repo-sandbox`.
> In the right sidebar, click the Milestone gear and assign
> "Test Roadmap Goal A".
>
> Then go check `scicomp-roadmap-sandbox` Issue A and confirm
> "Test work ticket 1" appears as a sub-issue.
>
> This confirms `link-issues-by-milestone.yml` is working end-to-end.

---

### Path B — Arielle's way (via project board field)

> **MANUAL STEP**: In your project board, find `Test work ticket 2`.
> Set the "Project Milestones" field to `Test Roadmap Goal A`.
>
> Then:
> 1. Check the Actions tab in `work-repo-sandbox` — you should see
>    `assign-milestone-from-board.yml` fire
> 2. Go to `Test work ticket 2` — it should now have the
>    "Test Roadmap Goal A" milestone assigned
> 3. Check that `link-issues-by-milestone.yml` also fired (it should
>    chain automatically)
> 4. Go to `scicomp-roadmap-sandbox` Issue A — both tickets 1 and 2
>    should appear as sub-issues
>
> This confirms the full board-to-roadmap chain is working.

---

### Path C — Quarterly URL swap (ongoing support pattern)

> **MANUAL STEP**: Go to `work-repo-sandbox/milestones`, find
> "Test Roadmap Goal A", click Edit, and change the description URL
> to point to Issue B instead.
>
> Now assign `Test work ticket 3` to the "Test Roadmap Goal A" milestone
> (whose URL now points to Issue B).
>
> Confirm that ticket 3 appears as a sub-issue on **Issue B**, not Issue A.
>
> This demonstrates the quarterly URL swap pattern for ongoing support items.

---

## Phase 5: Invite collaborators to demo

> **MANUAL STEP**: In both repos:
> Settings → Collaborators → Add people
>
> Add Dan, Arielle, Jon, or whoever you want to walk through the demo with.
> They'll be able to see everything and try the workflows themselves.

---

## What to do after the sandbox is validated

Once you're confident everything works:

1. **`create-milestones.yml`** → PR to `aind-scientific-computing`
   (update owner from `dougollerenshaw` to `AllenNeuralDynamics`)

2. **`link-issues-by-milestone.yml`** → PR to each downstream repo
   (update targetOwner/targetRepo to `AllenNeuralDynamics`/`aind-scientific-computing`)
   Use the batch PR script (`open_linking_prs.py`) for this.

3. **`assign-milestone-from-board.yml`** → coordinate with whoever owns
   `AllenNeuralDynamics/.github` to add it there, and update the field name
   to match Arielle's actual field name ("Project Milestones").

4. **Arielle's board**: Update each "Project Milestones" option description
   to contain the corresponding SciComp roadmap issue URL.

5. **Issue template**: Add the `Linked Repositories` field to
   `.github/ISSUE_TEMPLATE/milestone.yml` in `aind-scientific-computing`
   (PR already drafted).

6. **Backfill**: Run the one-time backfill script (to be written, similar to
   `build_repo_matrix.py`) to create milestones in downstream repos for
   all existing open roadmap items.