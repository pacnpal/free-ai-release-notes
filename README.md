# free-ai-release-notes

A GitHub Action (also available as a [reusable workflow](#reusable-workflow)) that writes your release **titles** and **release notes** with AI, for free, using free models on [OpenRouter](https://openrouter.ai): NVIDIA's Nemotron models by default, with OpenRouter's [free models router](https://openrouter.ai/openrouter/free) as a fallback. Prefer a specific model? [Bring your own](#choosing-a-model).

It reads the commits (and, when allowed, the merged pull requests) between the previous tag and the new one, asks the model to summarise them into grouped, user-facing Markdown notes and a short title, and then either creates/updates the GitHub release for you or hands the title and notes to the rest of your workflow. [Breaking changes come first.](#breaking-changes)

```text
v1.4.0: Offline mode and faster sync

### ⚠️ Breaking Changes
- The `sync.legacy` option has been removed; delete it from your config (#141)

This release adds offline support and makes syncing noticeably faster on large projects.

### ✨ New Features
- Work offline; changes sync automatically when you reconnect (#142)

### 🐛 Bug Fixes
- Fix a crash when opening an empty project (#139)

### ⚡ Performance
- Sync large projects up to 3x faster (#140)

**Full Changelog**: https://github.com/you/app/compare/v1.3.2...v1.4.0
```

## Contents

- [Quick start](#quick-start)
- [Set it up with an AI agent](#set-it-up-with-an-ai-agent)
- [Setting up OPENROUTER_API_KEY](#setting-up-openrouter_api_key)
- [Usage examples](#usage-examples)
- [Choosing a model](#choosing-a-model)
- [Breaking changes](#breaking-changes)
- [Inputs](#inputs)
- [Outputs](#outputs)
- [Permissions](#permissions)
- [How it works](#how-it-works)
- [Free tier limits and fallback](#free-tier-limits-and-fallback)
- [Privacy](#privacy)
- [Troubleshooting](#troubleshooting)
- [Pinning a version](#pinning-a-version)
- [Developing this repository](#developing-this-repository)

## Quick start

1. [Create an OpenRouter API key](https://openrouter.ai/keys). A free account works; [adding $10 of credit](#free-tier-limits-and-fallback) is optional and raises the free-model limit from 50 to 1,000 requests a day.
2. In **each repository** that will use the action, add it as a secret named `OPENROUTER_API_KEY` (see [below](#setting-up-openrouter_api_key)).
3. Add `.github/workflows/release.yml` to that repository:

   ```yaml
   name: Release

   on:
     push:
       tags:
         - 'v*'

   permissions:
     contents: write

   jobs:
     release:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v5
           with:
             fetch-depth: 0

         - uses: pacnpal/free-ai-release-notes@v1
           with:
             openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}
             create-release: true
   ```

4. Push a tag:

   ```bash
   git tag v1.0.0
   ```

   ```bash
   git push origin v1.0.0
   ```

   The workflow creates the `v1.0.0` release with an AI-generated title and notes. The notes also appear in the job summary.

The action reads the history since the previous tag from the checkout, so check out with `fetch-depth: 0`. If you don't, it fetches the full history and tags itself, which needs the checkout's default `persist-credentials: true`.

## Set it up with an AI agent

Using a coding agent such as Claude Code, Codex or Copilot? Paste this prompt into it from your repository. It adds the action to the workflow that already makes your releases, or creates a release workflow if there isn't one.

```text
Add AI-written release titles and notes to this repository with the GitHub Action
pacnpal/free-ai-release-notes@v1. Read its README first for the inputs, outputs and
permissions: https://github.com/pacnpal/free-ai-release-notes#readme

1. Look in .github/workflows/ for a workflow that already creates or publishes GitHub
   releases (it runs on tag pushes or `release: published`, or calls `gh release create`
   or a release action). If there is one, change it instead of adding a second workflow,
   and keep its triggers, build steps and uploaded assets as they are:
   - If a step creates the release itself, add the action before it with `id: notes` and
     without `create-release`, then give that step `steps.notes.outputs.title` as the
     title and `steps.notes.outputs.notes-file` as the body (`--notes-file` for gh,
     `body_path` for most release actions). Turn off any notes it generates itself, such
     as `generate_release_notes: true`. Pass the outputs through `env:`; never put
     `${{ steps.notes.outputs.notes }}` inside a `run:` script.
   - If the workflow runs on `release: published`, add the action with
     `create-release: true`; it rewrites that release's title and notes in place.
   - If a tool such as release-please or semantic-release creates the tag and release,
     add the action after it, only when a release was made, with `tag` set to the tag it
     created and `create-release: true`. Run `git fetch --tags --force` first so the new
     tag is in the checkout.
2. If there is no release workflow, create .github/workflows/release.yml that runs when a
   tag in this repository's tag style (`v*` if there are no tags yet) is pushed and runs
   the action with `create-release: true`, like the README's Quick start.
3. The job needs `permissions: contents: write`, and `actions/checkout` with
   `fetch-depth: 0` before the action.
4. Pass the key as `openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}`. Don't ask me
   for the key and don't write it into any file.
5. If the repository has more than one tag series (a monorepo, or a moving major tag such
   as `v1`), set `tag-pattern` so the previous tag comes from the same series, e.g.
   `v*.*.*`.
6. Leave `model` unset so the free default models are used, unless I asked for another.
7. Lint the workflow with actionlint if you can.

Don't push a tag or publish a release to test it. When you're done, tell me which file
you changed or created and what triggers it, and remind me to create a key at
https://openrouter.ai/keys and add it as the repository secret OPENROUTER_API_KEY
(Settings > Secrets and variables > Actions, or `gh secret set OPENROUTER_API_KEY`).
```

## Setting up OPENROUTER_API_KEY

The key is **required**, and it must be set in every repository that uses the action. The action stops at its first step with an error explaining what to do if the key is missing.

**From the GitHub UI:** repository **Settings → Secrets and variables → Actions → New repository secret**, name `OPENROUTER_API_KEY`, value your key.

**With the GitHub CLI** (run inside the repository; it prompts for the value):

```bash
gh secret set OPENROUTER_API_KEY
```

Then pass it to the action:

```yaml
        with:
          openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}
```

> An organization secret works too, as long as it is made available to the repository; it is still read as `secrets.OPENROUTER_API_KEY` in the workflow.

## Usage examples

Ready-to-copy workflows live in [`examples/`](examples):

| File | When it runs | What it does |
| --- | --- | --- |
| [`release-on-tag.yml`](examples/release-on-tag.yml) | A `v*` tag is pushed | Creates the release with AI title and notes |
| [`release-on-publish.yml`](examples/release-on-publish.yml) | A release is published in the UI | Replaces that release's title and notes in place |
| [`manual-release.yml`](examples/manual-release.yml) | Run by hand with a version | Creates a draft release (and tag) from the chosen branch |
| [`use-outputs.yml`](examples/use-outputs.yml) | A `v*` tag is pushed | Only generates text; your own step builds and publishes |
| [`reusable-workflow.yml`](examples/reusable-workflow.yml) | A `v*` tag is pushed | The quick start as a [reusable workflow](#reusable-workflow) |

The snippets below show only the action step; each job also needs `runs-on` and the `actions/checkout` step from the [quick start](#quick-start).

### Create the release on tag push

See [Quick start](#quick-start).

### Rewrite a release you publish by hand

```yaml
on:
  release:
    types: [published]

permissions:
  contents: write

# ...
      - uses: pacnpal/free-ai-release-notes@v1
        with:
          openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}
          create-release: true # an existing release is updated, not duplicated
```

### Release a tag that doesn't exist yet

Pass `tag` (and optionally `target`); the release, and the tag, are created on that commit.

```yaml
on:
  workflow_dispatch:
    inputs:
      version:
        required: true

permissions:
  contents: write

# ...
      - uses: pacnpal/free-ai-release-notes@v1
        with:
          openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}
          tag: ${{ inputs.version }}
          target: ${{ github.sha }}
          draft: true
          create-release: true
```

### Use the title and notes in your own release step

Leave `create-release` off and read the outputs in a later step:

```yaml
      - id: notes
        uses: pacnpal/free-ai-release-notes@v1
        with:
          openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}

      - env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ steps.notes.outputs.tag }}
          TITLE: ${{ steps.notes.outputs.title }}
          NOTES_FILE: ${{ steps.notes.outputs.notes-file }}
        run: gh release create "$TAG" --title "$TITLE" --notes-file "$NOTES_FILE"
```

This also works with any release action, e.g. `name: ${{ steps.notes.outputs.title }}` and `body_path: ${{ steps.notes.outputs.notes-file }}`.

> Pass the outputs through `env:` as shown rather than writing `${{ steps.notes.outputs.notes }}` directly inside a `run:` script: the notes are model-generated text and should never be pasted into shell code.

### Steer the writing

```yaml
        with:
          instructions: |
            Audience is non-technical end users. Keep it under 10 bullets.
            Call out anything that requires a config change in a "Breaking Changes" section.
          title-template: '{title} ({tag})'
```

### Monorepos and multiple tag series

Use `tag-pattern` so the previous tag is picked from the same series:

```yaml
        with:
          tag-pattern: 'api-v*'
```

or set `previous-tag` explicitly. If you also keep a moving major tag such as `v1`, use `tag-pattern: 'v*.*.*'` so it isn't picked as the previous release.

### Stable releases and prereleases

By default the previous tag is picked from the same kind of release (`match-release-type: true`):

| Tags so far | New tag | Compared against | Why |
| --- | --- | --- | --- |
| `v1.0.0`, `v1.1.0-beta.1`, `v1.1.0-beta.2` | `v1.1.0` | `v1.0.0` | A stable release covers everything since the last stable one, betas included. |
| `v1.1.0-beta.2`, `v1.1.0`, `v1.1.1` | `v1.2.0-beta.1` | `v1.1.0-beta.2` | A prerelease covers everything since the last prerelease. |
| `v1.0.0` (no prereleases yet) | `v1.1.0-rc.1` | `v1.0.0` | With no earlier prerelease, the last stable tag is used. |

A tag is a prerelease if its version has a suffix: SemVer's `-beta.1`, `-rc.1`, `-alpha` and so on (`v2.0.0-rc.1`, `api-v1.2.0-beta.1`), or a PEP 440 label (`2.0.0b1`, `2.0rc1`, `1.4.dev2`). The new release also counts as a prerelease when `prerelease: true`. Build metadata (`v1.2.3+build.5`) and tags without a `major.minor` version (`v1`, `latest`) count as stable. Set `match-release-type: false` to compare against the closest tag of either kind, or set `previous-tag` to choose it yourself.

### Reusable workflow

If you'd rather call a whole job than add steps, the same logic is available as a reusable workflow. It checks out your repository itself, and takes the key as a secret:

```yaml
jobs:
  release:
    uses: pacnpal/free-ai-release-notes/.github/workflows/generate-release-notes.yml@v1
    with:
      create-release: true
    secrets:
      OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }} # or: secrets: inherit
```

It takes the same [inputs](#inputs) (except `openrouter-api-key` and `github-token`) plus `runs-on`, and its outputs are read from `needs.<job>.outputs`. It runs the action from the same commit you call it at, so pinning the workflow pins the action too. It needs github.com: GitHub Enterprise Server doesn't provide the `job.workflow_*` context it relies on, so use the action there.

## Choosing a model

The default costs nothing: `nvidia/nemotron-3-ultra-550b-a55b:free, nvidia/nemotron-3.5-super-vl:free, openrouter/free`. NVIDIA's Nemotron 3 Ultra answers first, Nemotron 3.5 Super VL takes over if it's busy, and OpenRouter's free router picks any other free model as a last resort. Both Nemotron models produced usable notes on every test request with these settings. To use a model you choose, set `model` to any [OpenRouter model ID](https://openrouter.ai/models):

```yaml
        with:
          model: anthropic/claude-sonnet-4.5
```

Paid models are billed to your OpenRouter account and need credits on it.

**Fallbacks.** List several models, separated by commas or new lines, and OpenRouter tries them in order when one fails (an error, downtime, rate limiting or no credits left). Ending the list with `openrouter/free` keeps releases going for free if your preferred model is unavailable:

```yaml
        with:
          model: anthropic/claude-sonnet-4.5, openrouter/free
```

You're billed for whichever model actually answers; the `model` output says which one it was. To guarantee a release costs nothing, list only `openrouter/free` or models ending in `:free`.

**Per-repository default without editing the workflow.** Read the model from a repository or organization [variable](https://docs.github.com/actions/learn-github-actions/variables); when it isn't set, `model` is empty and the free default applies:

```yaml
        with:
          model: ${{ vars.OPENROUTER_MODEL }}
```

```bash
gh variable set OPENROUTER_MODEL --body "anthropic/claude-sonnet-4.5, openrouter/free"
```

An empty `model` means the free default. If OpenRouter stops recognising a model in the list (for example, a free model that was retired), the action drops it, warns, and tries the rest.

## Breaking changes

The model is instructed in no uncertain terms to put breaking changes first, above the summary:

- **Detected from commits.** Commits marked as breaking with [Conventional Commits](https://www.conventionalcommits.org/) (`feat!: ...`, `fix(api)!: ...`, or a `BREAKING CHANGE: ...` footer) are collected across the whole release range, even beyond `max-commits`. They're handed to the model in full as changes it **must** list, each ending with its commit hash, and the prompt ends with a reminder of how many there are. Footers are read carefully:
  - multi-line footers keep their indentation, blank lines and code examples (e.g. a YAML migration snippet), and end at the next trailer such as `Refs:` or `Signed-off-by:`;
  - a commit with several `BREAKING CHANGE:` footers lists each of them;
  - an empty `BREAKING CHANGE:` footer still marks the commit as breaking;
  - `BREAKING CHANGE:` lines inside a code block, such as a documented example, are ignored.
- **Recognised by the model.** The model is also told what counts as breaking even without a marker: removed or renamed APIs, options, commands and settings, changed defaults or behaviour, newly required configuration, and dropped platform support.
- **First, every time.** The prompt makes this its overriding rule: when there is any breaking change, the very first line of the notes must be `### ⚠️ Breaking Changes`, with each item saying what changed and what users must do to upgrade, and breaking changes may not appear anywhere else.
- **The model's notes are published as written.** The workflow doesn't rearrange them. If the model's notes don't mention a flagged commit by hash, the job logs a warning naming it so you can spot it.
- **Kept in the fallback.** When AI generation fails, the fallback notes start with a **⚠️ Breaking Changes** section built from the flagged commits.

Free models vary, so how faithfully the rules are followed depends on the model that answers. For the most consistent results, set `model` to a specific, capable model (see [Choosing a model](#choosing-a-model)).

Marking breaking commits with `!` or `BREAKING CHANGE:` is the most reliable way to make sure nothing is missed.

## Inputs

Only `openrouter-api-key` is required.

| Input | Default | Description |
| --- | --- | --- |
| `openrouter-api-key` | | **Required.** Your OpenRouter API key; pass `${{ secrets.OPENROUTER_API_KEY }}`. |
| `tag` | triggering tag | Tag to generate notes for. Defaults to `github.ref_name` when the workflow runs on a tag push or release event; required otherwise. |
| `previous-tag` | auto | Tag to compare against. Defaults to the closest tag of the same release type reachable from the parent of the release commit (see `match-release-type`). Empty on a first release (the whole history is used). |
| `match-release-type` | `true` | Pick the previous tag from the same kind of release: a stable release is compared against the last stable tag, so it covers every change since then, prereleases included; a prerelease against the last prerelease, or the last stable tag if there's none. `false` compares against the closest tag of either kind. See [Stable releases and prereleases](#stable-releases-and-prereleases). |
| `target` | `github.sha` | Commit-ish to release when `tag` doesn't exist yet. Ignored if the tag exists. |
| `tag-pattern` | | Glob for picking the previous tag automatically (`git describe --match`), e.g. `v*`. |
| `model` | free Nemotron models, then `openrouter/free` | OpenRouter model ID, or several separated by commas/new lines to fall back in order. Empty means `nvidia/nemotron-3-ultra-550b-a55b:free, nvidia/nemotron-3.5-super-vl:free, openrouter/free`. See [Choosing a model](#choosing-a-model). |
| `instructions` | | Extra instructions added to the prompt. |
| `title-template` | `{tag}: {title}` | Release title format. `{tag}` is the tag, `{title}` the AI title. When the fallback is used, the title is just the tag. |
| `max-commits` | `200` | Maximum commits sent to the model. |
| `max-input-chars` | `60000` | Maximum characters of git context sent to the model. Commits flagged as breaking are always sent in full and don't count towards it. |
| `temperature` | `0.3` | Sampling temperature. |
| `max-tokens` | `16384` / `4096` | Maximum tokens in the response, including the model's hidden reasoning. Empty means `16384` when every model is free (free models are all reasoning models and can use thousands of tokens before they answer) and `4096` otherwise, because OpenRouter holds a paid request's `max-tokens` cost against your balance while it runs. |
| `retries` | `3` | Attempts against OpenRouter before giving up. Each attempt may land on a different free model. |
| `use-github-notes` | `true` | Also send GitHub's own generated notes (merged PRs with authors, new contributors) as context. Needs `contents: write`; skipped silently without it. |
| `append-changelog-link` | `true` | Append a **Full Changelog** compare link. |
| `fail-on-error` | `false` | Fail the job if AI generation fails, instead of using the fallback. |
| `create-release` | `false` | Create the release, or update its title and notes if it already exists. Needs `contents: write`. |
| `draft` | `false` | Create the release as a draft (new releases only). |
| `prerelease` | `false` | Mark the release as a prerelease (new releases only). |
| `api-base-url` | `https://openrouter.ai/api/v1` | OpenRouter API base URL. |
| `github-token` | `github.token` | Token for GitHub's generated notes and for creating the release. |

The runner needs `bash`, `git`, `python3` and, for `create-release`, `gh`; GitHub's Ubuntu and macOS runners have them all.

The [reusable workflow](#reusable-workflow) takes the API key as the `OPENROUTER_API_KEY` secret instead of an input, has no `github-token` input, and adds `runs-on` (runner label, default `ubuntu-latest`).

## Outputs

| Output | Description |
| --- | --- |
| `title` | Release title (after `title-template`). |
| `notes` | Release notes in Markdown. |
| `notes-file` | Path to a file with the release notes (action only). |
| `tag` | Tag the notes were generated for. |
| `previous-tag` | Tag the changes were compared against (empty on a first release). |
| `model` | The model that actually answered, e.g. `nvidia/nemotron-3-ultra-550b-a55b:free`. Empty when the fallback was used. |
| `ai-generated` | `'true'` if the notes came from the model, `'false'` if the fallback was used. |
| `release-url` | URL of the created or updated release (only with `create-release: true`). |

## Permissions

The action uses the workflow's `GITHUB_TOKEN` (or `github-token`), so it can do what your workflow's `permissions:` grant. The reusable workflow doesn't declare permissions either; it runs with what the caller grants.

| You want | Workflow needs |
| --- | --- |
| Generate text only, from git history | `contents: read` |
| Include merged PRs / contributors as context (`use-github-notes`) | `contents: write` |
| Create or update the release (`create-release`) | `contents: write` |

## How it works

1. **Checks** that the OpenRouter key is set and stops with instructions if not.
2. **Uses your checkout** of the repository, fetching the full history and tags if it is shallow. (The reusable workflow checks out your repository with full history itself.)
3. **Works out the range**: the release tag (or `target` if the tag isn't created yet) and the previous tag of the same release type: the last stable tag for a stable release, the last prerelease for a prerelease.
4. **Collects context**: commits flagged as breaking, commit subjects and bodies (merges excluded, up to `max-commits`), a diffstat of changed files, and GitHub's generated notes when permitted, trimmed to `max-input-chars` (the flagged breaking commits are always sent in full).
5. **Calls OpenRouter** with the models in `model` (by default Nemotron 3 Ultra, then Nemotron 3.5 Super VL, then the free router, which picks a free model at random); OpenRouter moves down the list when a model errors or is busy. The model is asked for JSON with a `title` and Markdown `notes`: Breaking Changes first, then a summary, then New Features, Bug Fixes, Performance, Documentation and Maintenance. It is told not to invent changes. The answer is parsed defensively (code fences and `<think>` blocks are stripped) and validated.
6. **Retries** on rate limits, server errors and unusable answers with backoff (5s, 10s, 20s, ...). If a model rejects JSON mode, later attempts drop it. An HTTP `402` caused by OpenRouter's temporary in-flight spending hold is retried after its `Retry-After`; any other `402` (insufficient credits) stops retrying and uses the fallback, and so does a `429` saying the daily free-model limit is used up.
7. **Checks breaking changes**: logs a warning for any flagged breaking commit the model's notes don't mention (see [Breaking changes](#breaking-changes)).
8. **Writes outputs** and a preview to the job summary, and with `create-release: true` creates the release (`gh release create`) or edits the existing one (`gh release edit`). Notes longer than GitHub's 125,000-character release limit are cut at a line boundary with a note saying so.

Model output is never printed to the log or executed: it only goes to step outputs, a Markdown file and the job summary.

## Free tier limits and fallback

Free models cost nothing, but OpenRouter limits how often you can call them, per account ([OpenRouter's limits](https://openrouter.ai/docs/api-reference/limits)):

| Credits ever bought | Free-model requests per minute | Free-model requests per day |
| --- | --- | --- |
| Less than $10 | 20 | 50 |
| $10 or more | 20 | 1,000 |

One release uses one request, plus one per retry. The daily cap is shared by every repository and workflow using the same key, including test runs, so 50 a day can run out on a busy day, and then releases fall back to non-AI notes until midnight UTC.

**Adding $10 of credit is worth it if you release often or share one key across repositories.** It raises the cap to 1,000 requests a day, and free models still cost $0, so the credit isn't used up by this action. You only spend it if you set `model` to a paid model. Add it at [openrouter.ai/settings/credits](https://openrouter.ai/settings/credits). Keep the balance from going negative: a negative balance blocks free models too.

All of OpenRouter's free models reason before answering, and that reasoning counts against `max-tokens`. When every model in `model` is free, the action asks for low reasoning effort and allows 16,384 tokens so there's room left for the answer. Paid models aren't sent a reasoning effort, so their own defaults apply.

Free models vary in quality and formatting, especially when the free router picks one at random. The workflow handles that by validating the answer and retrying. If every attempt fails:

- with `fail-on-error: false` (default) it **falls back** to GitHub's generated notes, or a plain commit list, with the tag as the title, emits a warning, and sets `ai-generated` to `false`; the release still goes out.
- with `fail-on-error: true` the job fails.

If you want more consistent output, set `model` to a paid model with the free default as a fallback (see [Choosing a model](#choosing-a-model)).

## Privacy

Commit messages, changed file names and PR titles from the release range are sent to OpenRouter and the model provider that serves the request. Some free providers log prompts or may use them for training, which OpenRouter lets you control in your [privacy settings](https://openrouter.ai/settings/privacy). Don't use this on repositories whose commit history must not leave GitHub.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `OpenRouter API key is not set` / `OPENROUTER_API_KEY is not set` | Add the secret to this repository and pass it as `openrouter-api-key` (action) or under `secrets:` (reusable workflow). Secrets aren't available to workflows triggered from forks. |
| `No git repository here` | Add `actions/checkout` with `fetch-depth: 0` before the action. |
| `OpenRouter rejected OPENROUTER_API_KEY (HTTP 401)` | The key is wrong or revoked; create a new one and update the secret. |
| Warnings with HTTP `404` "No endpoints found matching your data policy" | Your OpenRouter privacy settings exclude every free provider. Allow free endpoints in [privacy settings](https://openrouter.ai/settings/privacy). |
| Warning with HTTP `402` | If it says the in-flight spending budget is temporarily full, the workflow waits for OpenRouter's `Retry-After` and retries on its own. Otherwise it means insufficient credits (the warning includes OpenRouter's hint); the workflow stops retrying and uses the fallback notes. With a paid model, add credits or add `openrouter/free` as a fallback in `model`. If you're already on free models, your OpenRouter balance is negative, which blocks free models too: add credits. |
| Warnings with HTTP `429` | Free-tier rate limit. Raise `retries`, or wait; the fallback still publishes the release. If the warning says the daily limit is used up, retrying won't help until it resets (midnight UTC), so the action stops and uses the fallback. Adding $10 of credit raises the limit from 50 to 1,000 requests a day (see [Free tier limits](#free-tier-limits-and-fallback)). |
| `the model ran out of max-tokens before finishing its answer` | The model used up `max-tokens` before writing a complete answer. With free models this is usually hidden reasoning; the warning shows the reasoning-token count when OpenRouter reports one. The next attempt usually lands on a different free model. If it keeps happening, raise `max-tokens` or set `model` to a model that answers reliably. |
| `No tag to release` | The workflow didn't run on a tag. Pass `tag:`. |
| `Resource not accessible by integration` when creating the release | The workflow needs `permissions: contents: write`. |
| Notes compare against the wrong tag | Set `tag-pattern` or `previous-tag`. |
| A breaking change isn't listed, or a warning says a flagged commit isn't mentioned | Mark breaking commits with `!` (e.g. `feat!: ...`) or a `BREAKING CHANGE:` footer so they're handed to the model as mandatory. If a free model still leaves one out, re-run the job or set `model` to a more capable model. |
| `Release notes exceeded GitHub's 125,000-character limit` | The notes were cut at a line boundary to fit GitHub's release body limit. Breaking changes come first, so they survive unless the breaking-change list alone is that long. Lower `max-commits` or narrow the range with `previous-tag`. |
| `ai-generated` is `false` | All attempts failed; the job's warnings say why. |

## Pinning a version

`@v1` follows the latest `v1.x.y` release. To control updates, pin an exact release or, most strictly, a commit SHA:

```yaml
      - uses: pacnpal/free-ai-release-notes@v1.2.0
```

```yaml
      - uses: pacnpal/free-ai-release-notes@<commit-sha>
```

The same refs work for the reusable workflow (`pacnpal/free-ai-release-notes/.github/workflows/generate-release-notes.yml@v1`). `@main` runs unreleased changes.

For private or internal repositories, this repository must be accessible to the caller (public, or shared under **Settings → Actions → General → Access**). If you host the reusable workflow in a private or internal repository, also pass a token that can read it (for example a fine-grained token with `contents: read` on it) as the `WORKFLOW_REPO_TOKEN` secret: the workflow checks that repository out to run the action, and the caller's `github.token` can't read it. The action itself needs no token for this.

## Developing this repository

- [`action.yml`](action.yml) is the action. It runs [`src/generate_notes.py`](src/generate_notes.py), which holds all the logic, then creates or updates the release with `gh`.
- [`.github/workflows/generate-release-notes.yml`](.github/workflows/generate-release-notes.yml) is the reusable workflow: it checks out the caller's repository and this one (at the commit it was called at) and runs the action.
- [`.github/workflows/test.yml`](.github/workflows/test.yml) runs the action, from both a full and a shallow checkout, and the reusable workflow against this repository on every push and pull request, without creating a release (needs the `OPENROUTER_API_KEY` secret here).
- [`.github/workflows/release.yml`](.github/workflows/release.yml) releases this repository with its own action and moves the major tag (`v1`) to the newest release.
- [`AGENTS.md`](AGENTS.md) (imported by `CLAUDE.md`) tells coding agents how to work here, including that they release only when asked.
- [`.github/workflows/lint.yml`](.github/workflows/lint.yml) runs [actionlint](https://github.com/rhysd/actionlint) over the workflows and examples.

To release, either push a `vX.Y.Z` tag, or run the Release workflow by hand on `main` (**Actions → Release → Run workflow**, or `gh workflow run release.yml --ref main -f version=vX.Y.Z`), which creates the tag for you. Running it for a version that already exists regenerates that release's title and notes without moving its tag. To show a release on the GitHub Marketplace, edit it on GitHub and tick **Publish this Action to the GitHub Marketplace** (the first time, you'll be asked to accept the Marketplace Developer Agreement and pick a category).

## License

[MIT](LICENSE)
