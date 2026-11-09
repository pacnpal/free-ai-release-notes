"""Generate a release title and notes from git history with OpenRouter.

Run by action.yml (which the reusable workflow also calls). Inputs arrive as IN_* environment
variables, the API key as OPENROUTER_API_KEY and the token as GITHUB_TOKEN; results are
written to GITHUB_OUTPUT. The current directory must be a checkout of the repository to release.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
import uuid


def env(name, default=""):
    return os.environ.get(name, default).strip()


def env_bool(name):
    return env(name).lower() == "true"


def env_num(name, default, cast=int):
    try:
        return cast(float(env(name)))
    except ValueError:
        return default


def git(*args, check=True):
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        sys.exit(f"::error::git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.rstrip() if proc.returncode == 0 else ""


def set_output(name, value):
    delim = f"EOF_{uuid.uuid4().hex}"
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"{name}<<{delim}\n{value}\n{delim}\n")


def log(level, message):
    # Keep model output out of the log: it could contain workflow commands. Messages can still carry
    # API error text, so escape them as command data: a newline must not start a new command.
    message = str(message).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{level}::{message}", flush=True)


repo = env("GITHUB_REPOSITORY")
server = env("GITHUB_SERVER_URL", "https://github.com")
api_url = env("GITHUB_API_URL", "https://api.github.com")

# ------------------------------------------------------------ checkout
if git("rev-parse", "--is-inside-work-tree", check=False) != "true":
    sys.exit("::error::No git repository here. Add `actions/checkout` with `fetch-depth: 0` before this action.")
if git("rev-parse", "--is-shallow-repository", check=False) == "true":
    # actions/checkout fetches a single commit by default; the previous tag and the commits
    # since it need the full history.
    print("Shallow clone detected; fetching full history and tags (use `fetch-depth: 0` to skip this).")
    proc = subprocess.run(["git", "fetch", "--quiet", "--unshallow", "--tags", "origin"], capture_output=True, text=True)
    if proc.returncode != 0:
        log("warning", "Could not fetch full history; the notes may miss commits. Check out with `fetch-depth: 0`. "
            f"git fetch: {proc.stderr.strip()[:300]}")

# ---------------------------------------------------------------- refs
tag = env("IN_TAG")
if not tag and env("GITHUB_REF_TYPE") == "tag":
    tag = env("GITHUB_REF_NAME")
if not tag:
    sys.exit("::error::No tag to release. Pass the `tag` input or run the caller on a tag push / release event.")

tag_exists = bool(git("rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", check=False))
head_ref = tag if tag_exists else (env("IN_TARGET") or env("GITHUB_SHA"))
head_sha = git("rev-parse", f"{head_ref}^{{commit}}")

# A prerelease has a suffix right after its version number: SemVer's "-beta.1" (v2.0.0-beta.1,
# api-v1.2.0-rc.1) or a PEP 440 style label (2.0.0b1, 2.0rc1, 1.4.dev2). Build metadata ("+build")
# and tags without a major.minor version (v1, latest) count as stable.
VERSION_CORE = re.compile(r"\d+\.\d+(?:\.\d+)*")
PRERELEASE_SUFFIX = re.compile(r"^(?:-.|[._]?(?:alpha|beta|rc|pre|preview|dev|a|b|c)\.?\d*(?![A-Za-z]))", re.I)


def is_prerelease(name):
    version = VERSION_CORE.search(name)
    return bool(version and PRERELEASE_SUFFIX.match(name[version.end():]))


def closest_tag(keep=None):
    """The closest tag reachable from the parent of the release commit that matches tag-pattern
    and, if given, keep(name); empty if there is none."""
    pattern = env("IN_TAG_PATTERN")
    matches = [f"--match={pattern}"] if pattern else []
    if keep:
        listed = git("tag", "--list", *([pattern] if pattern else []), check=False).splitlines()
        # Tag names can't contain glob characters, so each name only matches itself.
        matches = [f"--match={name}" for name in listed if name and name != tag and keep(name)]
        if not matches:
            return ""
    found = git("describe", "--tags", "--abbrev=0", *matches, f"{head_sha}^", check=False)
    return "" if found == tag else found


release_is_prerelease = env_bool("IN_PRERELEASE") or is_prerelease(tag)
release_type = "prerelease" if release_is_prerelease else "stable release"
previous_tag = env("IN_PREVIOUS_TAG")
previous_reason = "the previous-tag input"
if previous_tag:
    if not git("rev-parse", "-q", "--verify", f"refs/tags/{previous_tag}^{{commit}}", check=False):
        sys.exit(f"::error::previous-tag '{previous_tag}' does not exist.")
elif not env_bool("IN_MATCH_RELEASE_TYPE"):
    previous_tag, previous_reason = closest_tag(), "the closest tag"
elif release_is_prerelease:
    # A prerelease covers everything since the last prerelease; the first one since the last
    # stable release if there has never been one.
    previous_tag, previous_reason = closest_tag(is_prerelease), "the last prerelease"
    if not previous_tag:
        previous_tag, previous_reason = closest_tag(lambda name: not is_prerelease(name)), "the last stable release"
else:
    # A stable release covers everything since the last stable release, prereleases in between included.
    previous_tag, previous_reason = closest_tag(lambda name: not is_prerelease(name)), "the last stable release"

rev_range = f"{previous_tag}..{head_sha}" if previous_tag else head_sha
print(f"Release: {tag} ({release_type}, {head_sha[:12]}), comparing against: "
      + (f"{previous_tag} ({previous_reason})" if previous_tag else "(beginning of history)"))

# ------------------------------------------------------------- context
max_commits = env_num("IN_MAX_COMMITS", 200)
total_commits = int(git("rev-list", "--count", "--no-merges", rev_range) or 0)
raw_log = git("log", "--no-merges", f"-n{max_commits}", "--format=%x1e%h%x1f%an%x1f%s%x1f%b", rev_range)
commit_lines = []
for entry in filter(None, raw_log.split("\x1e")):
    sha, author, subject, body = (entry.split("\x1f") + ["", "", "", ""])[:4]
    line = f"- {subject.strip()} ({sha}, {author})"
    body = "\n".join(f"    {b}" for b in body.strip().splitlines() if b.strip())
    commit_lines.append(f"{line}\n{body}" if body else line)
commits_text = "\n".join(commit_lines) or "(no commits)"
if total_commits > len(commit_lines):
    commits_text += f"\n... and {total_commits - len(commit_lines)} older commits not shown"

# Breaking changes flagged with Conventional Commits markers ("feat!:",
# "fix(api)!:" or a "BREAKING CHANGE:" footer), across the whole range.
BREAKING_SUBJECT = re.compile(r"^[A-Za-z]+(?:\([^)]*\))?!:\s*")
CONVENTIONAL_PREFIX = re.compile(r"^[A-Za-z]+(?:\([^)]*\))?!?:\s*")
BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGES?:\s*(.*)$")
# Any Conventional Commits / git trailer token, which ends a multi-line footer value.
FOOTER_TOKEN = re.compile(r"^(?:BREAKING[ -]CHANGES?|[A-Za-z][\w-]*)(?::\s|\s#)")


def fence_step(text, fence):
    """Return the code-fence state after one line: None outside a fence, else (character, length).

    A block opens with ``` or ~~~ and closes only with the same character, at least as many
    of them, and nothing after. A backtick run followed by more backticks is inline code.
    """
    run = re.match(r"^\s*(`{3,}|~{3,})(.*)$", text)
    if run and run.group(1)[0] == "`" and "`" in run.group(2):
        run = None
    if run and fence is None:
        return (run.group(1)[0], len(run.group(1)))
    if run and fence and run.group(1)[0] == fence[0] and len(run.group(1)) >= fence[1] and not run.group(2).strip():
        return None
    return fence


def breaking_footers(body):
    """Return every BREAKING CHANGE footer in a commit body, each as a list of lines
    (continuation lines included; [""] for an empty footer). Footer-like lines inside
    code blocks, e.g. a documented example, are ignored."""
    lines = body.splitlines()
    footers = []
    fence = None
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        match = None if fence else BREAKING_FOOTER.match(line)
        if not match:
            fence = fence_step(line, fence)
            continue
        value = [match.group(1).strip()]
        inner = fence_step(value[0], None)  # the footer may open a block itself: BREAKING CHANGE: ```yaml
        while i < len(lines):
            following = lines[i]
            if inner is None and FOOTER_TOKEN.match(following):
                break  # the next footer (possibly another BREAKING CHANGE) starts here
            inner = fence_step(following, inner)  # inside a block, "key: value" lines are content
            value.append(following.rstrip())
            i += 1
        while len(value) > 1 and not value[-1].strip():
            value.pop()
        footers.append(value)
    return footers


def footer_text(value, indent):
    """First line, then continuation lines with their relative indentation, indented under it.
    A footer whose first line opens a code block starts the block on its own line."""
    if re.match(r"^(`{3,}|~{3,})", value[0]):
        value = ["", *value]
    rest = textwrap.dedent("\n".join(value[1:])).strip("\n").splitlines()
    return value[0] + "".join(f"\n{indent}{line}" if line.strip() else "\n" for line in rest)


breaking_changes = []  # (short sha, subject without type prefix, Markdown bullet)
raw_breaking = git(
    "log", "--no-merges", "-E",
    "--grep=^[A-Za-z]+(\\([^)]*\\))?!:", "--grep=^BREAKING[ -]CHANGES?:",
    "--format=%x1e%h%x1f%s%x1f%b", rev_range,
)
for entry in filter(None, raw_breaking.split("\x1e")):
    sha, subject, body = (entry.split("\x1f") + ["", "", ""])[:3]
    subject = subject.strip()
    footers = breaking_footers(body)
    if not BREAKING_SUBJECT.match(subject) and not footers:
        continue
    sha, summary = sha.strip(), CONVENTIONAL_PREFIX.sub("", subject)
    item = f"- {summary} ({sha})"
    described = [value for value in footers if any(line.strip() for line in value)]  # skip empty footers
    if len(described) == 1:
        text = footer_text(described[0], "  ").rstrip()
        item += ":" + (text if text.startswith("\n") else f" {text}")
    elif described:
        # Several BREAKING CHANGE footers in one commit: one sub-bullet each.
        item += ":" + "".join(f"\n  - {footer_text(value, '    ')}".rstrip() for value in described)
    breaking_changes.append((sha, summary, item))
if breaking_changes:
    print(f"Detected {len(breaking_changes)} breaking change(s) from commit markers.")
breaking_text = "\n".join(item for _, _, item in breaking_changes)

diffstat = git("diff", "--stat=120", f"{previous_tag}..{head_sha}", check=False) if previous_tag else ""
stat_lines = diffstat.splitlines()
if len(stat_lines) > 80:
    diffstat = "\n".join(stat_lines[:79] + [stat_lines[-1]])

github_notes = ""
if env_bool("IN_USE_GITHUB_NOTES") and env("GITHUB_TOKEN"):
    payload = {"tag_name": tag, "target_commitish": head_sha}
    if previous_tag:
        payload["previous_tag_name"] = previous_tag
    req = urllib.request.Request(
        f"{api_url}/repos/{repo}/releases/generate-notes",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {env('GITHUB_TOKEN')}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            github_notes = json.load(resp).get("body", "").strip()
    except Exception as exc:  # noqa: BLE001 - best-effort context only
        print(f"GitHub generated notes unavailable ({exc}); continuing with git history only.")

budget = env_num("IN_MAX_INPUT_CHARS", 60000)
context_parts = []
if breaking_text:
    # Every flagged breaking change is mandatory, so this list is always sent in full and
    # max-input-chars applies to the rest of the context.
    context_parts.append(
        "## Breaking changes flagged in commit messages (every one MUST be listed under ⚠️ Breaking Changes)\n"
        + breaking_text
    )
sections = [
    ("GitHub generated notes (merged pull requests and contributors)", github_notes),
    ("Files changed", diffstat),
    ("Commits (newest first)", commits_text),
]
for heading, body in sections:
    if not body:
        continue
    block = f"## {heading}\n{body}"
    if len(block) > budget:
        block = block[: max(budget, 0)] + "\n... (truncated)"
    budget -= len(block)
    context_parts.append(block)
    if budget <= 0:
        break

# -------------------------------------------------------------- prompt
system_prompt = """You are a release notes writer. You turn git history into release notes for the people who use the software.
Respond with ONLY a JSON object, without code fences or any other text, of the form {"title": string, "notes": string}.

"title": a short, human-friendly release title (at most 60 characters) that captures the main theme of the release. Do not include the version number. No trailing period. No emoji.

"notes": GitHub-flavored Markdown that follows the rules below EXACTLY.

BREAKING CHANGES ALWAYS COME FIRST. THIS RULE OVERRIDES EVERY OTHER RULE.
- A breaking change is any change that forces users to change their code, configuration, scripts or workflows when they upgrade: removed or renamed APIs, options, commands, flags, files or settings; changed defaults or behaviour; newly required configuration; dropped platform, runtime or version support.
- Every item listed under "Breaking changes flagged in commit messages" IS a breaking change. You MUST include EVERY one of them. Never skip, merge away or downplay any of them, even if the change looks small or the input was truncated.
- If there is at least one breaking change, the VERY FIRST LINE of "notes" MUST be exactly: ### ⚠️ Breaking Changes
- Nothing may come before that heading: no summary, no title, no other heading, no blank line.
- Under that heading, write one bullet per breaking change. Each bullet MUST say what changed AND what users must do to upgrade. End the bullet of every flagged change with its short commit hash in parentheses, e.g. (a1b2c3d).
- Breaking changes MUST NOT appear under any other heading or anywhere else in the notes.
- If there are no breaking changes, leave the section out entirely. Never write "None" or an empty section.

After the breaking changes (or first, if there are none):
1. A 1-3 sentence summary of the release, as plain text with no heading.
2. The remaining changes grouped under these level-3 headings, in this order, leaving out any that would be empty: "### ✨ New Features", "### 🐛 Bug Fixes", "### ⚡ Performance", "### 📚 Documentation", "### 🔧 Maintenance".

Other rules:
- Write one concise, user-facing bullet per change and merge related commits into a single bullet.
- Keep pull request references (#123) and @mentions exactly as they appear in the input.
- Leave out noise such as merge commits, typo fixes and CI tweaks unless nothing else changed.
- Never invent changes that the input does not support.
- Do not add a top-level heading, the version number, or a "Full Changelog" link.

Layout when there are breaking changes:
### ⚠️ Breaking Changes
- <what changed>. <what users must do to upgrade>. (<commit hash>)

<summary>

### ✨ New Features
- <change>"""
system_prompt = "\n".join(line.strip() for line in system_prompt.splitlines())

user_prompt = "\n\n".join(
    [
        f"Repository: {repo}",
        f"Release: {tag} ({release_type})",
        f"Previous release: {previous_tag or 'none (first release)'}",
        *(["The changes below cover everything since the last stable release, including anything already "
           "published in prereleases since then. Describe them all as part of this release."]
          if previous_tag and not release_is_prerelease and previous_reason == "the last stable release" else []),
        f"Commits in this release: {total_commits}",
        *([f"Additional instructions from the maintainers:\n{env('IN_INSTRUCTIONS')}"] if env("IN_INSTRUCTIONS") else []),
        *context_parts,
        *([f"REMINDER: this release has {len(breaking_changes)} flagged breaking change(s). \"notes\" MUST start "
           "with the line ### ⚠️ Breaking Changes and list EVERY one of them first, each ending with its "
           "commit hash."] if breaking_changes else []),
    ]
)

# ---------------------------------------------------------- OpenRouter
def parse_response(content):
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, flags=re.S)
    if fenced:
        content = fenced.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("response contains no JSON object")
    data = json.loads(content[start : end + 1])
    title = data.get("title") if isinstance(data, dict) else None
    notes = data.get("notes") if isinstance(data, dict) else None
    if not isinstance(title, str) or not isinstance(notes, str):
        raise ValueError("response JSON is missing string 'title' / 'notes'")
    title = " ".join(title.split()).strip().strip("\"'`#*").rstrip(".").strip()
    notes = notes.strip()
    if not title or not notes:
        raise ValueError("response has an empty title or notes")
    return title[:100], notes


FREE_ROUTER = "openrouter/free"
# The default when `model` is empty. These answered every test request; the free router comes last
# in case both are busy.
DEFAULT_MODELS = ["nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3.5-super-vl:free", FREE_ROUTER]
models = [m.strip() for m in re.split(r"[,\n]", env("IN_MODEL")) if m.strip()] or list(DEFAULT_MODELS)
print(f"Model{'s' if len(models) > 1 else ''}: {', '.join(models)}")
# Every free model on OpenRouter is a reasoning model, and their reasoning counts against max_tokens.
def all_free():
    # Checked per request: dropping an unknown model can leave only free ones.
    return all(m == FREE_ROUTER or m.endswith(":free") for m in models)


def call_openrouter(use_json_mode):
    free = all_free()
    body = {
        "model": models[0],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": env_num("IN_TEMPERATURE", 0.3, float),
        # Free models need room to reason. Paid requests hold their max_tokens cost against the
        # account up front, so they keep a smaller budget unless `max-tokens` says otherwise.
        "max_tokens": env_num("IN_MAX_TOKENS", 16384 if free else 4096),
        "reasoning": {"exclude": True},
    }
    if free:
        # Keep reasoning short so it leaves room for the answer. Not sent for paid models: on
        # Claude, for example, an effort turns extended thinking on.
        body["reasoning"]["effort"] = "low"
    if len(models) > 1:
        body["models"] = models[1:]  # OpenRouter tries these in order if the first fails
    if use_json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        f"{env('IN_API_BASE_URL').rstrip('/')}/chat/completions",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {env('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
            "HTTP-Referer": f"{server}/{repo}",
            "X-Title": "free-ai-release-notes",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.load(resp)
    if data.get("error"):
        raise RuntimeError(f"OpenRouter error: {data['error']}")
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content")
    try:
        title, notes = parse_response(content)
    except ValueError as exc:
        reason = describe_response(data, choice, content)
        if choice.get("finish_reason") == "length":
            raise ValueError(f"the model ran out of max-tokens before finishing its answer ({reason})") from None
        raise ValueError(f"{exc} ({reason})") from None
    return title, notes, data.get("model", "")


def describe_response(data, choice, content):
    """Why an answer was unusable, from response metadata only (never the model's text)."""
    usage = data.get("usage") or {}
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    parts = [
        f"model {data.get('model') or 'unknown'}",
        f"finish_reason {choice.get('finish_reason') or 'unknown'}",
        f"{len(content or '')} characters of text",
    ]
    if usage.get("completion_tokens") is not None:
        parts.append(f"{usage['completion_tokens']} completion tokens"
                     + (f", {reasoning} of them reasoning" if reasoning else ""))
    return re.sub(r"[^\w .,:/()-]", "", ", ".join(parts))  # no workflow-command characters


ai_title = ai_notes = used_model = ""
attempts = max(env_num("IN_RETRIES", 3), 1)
use_json_mode = True
attempt = 0
while attempt < attempts:
    attempt += 1
    try:
        ai_title, ai_notes, used_model = call_openrouter(use_json_mode)
        print(f"Generated notes with {used_model or 'unknown model'} on attempt {attempt}.")
        break
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        detail = body_text[:500]
        if exc.code == 401:
            sys.exit("::error::OpenRouter rejected OPENROUTER_API_KEY (HTTP 401). Check the secret's value.")
        try:
            error = json.loads(body_text).get("error") or {}
        except (ValueError, AttributeError):
            error = {}
        metadata = error.get("metadata") or {} if isinstance(error, dict) else {}
        unknown = re.match(r"(\S+) is not a valid model ID", str(error.get("message", "")) if isinstance(error, dict) else "")
        if exc.code == 400 and unknown and unknown.group(1) in models and len(models) > 1:
            # One unknown model rejects the whole request, fallbacks included (e.g. a free model
            # that was retired). Drop it and try the rest without using up an attempt.
            models.remove(unknown.group(1))
            log("warning", f"OpenRouter doesn't know the model {unknown.group(1)}; trying {', '.join(models)}.")
            attempt -= 1
            continue
        if exc.code == 429 and metadata.get("limit_source") == "openrouter_free_tier_daily":
            # The daily cap on free-model requests: nothing succeeds again until it resets.
            hint = metadata.get("remedy_hint") or "Wait for the daily reset, or buy credits to raise the limit."
            log("warning", f"OpenRouter's daily limit on free-model requests is used up (HTTP 429). {hint}")
            break
        if exc.code == 402:
            if metadata.get("limit_source") == "openrouter_in_flight_budget":
                # A temporary hold while recent paid requests settle: wait for Retry-After and retry.
                try:
                    wait = min(max(float(exc.headers.get("Retry-After", "")), 1.0), 120.0)
                except ValueError:
                    wait = min(5 * 2 ** (attempt - 1), 60)
                retrying = f"retrying in {wait:.0f}s" if attempt < attempts else "no attempts left"
                log("warning", f"Attempt {attempt}/{attempts}: OpenRouter's in-flight spending budget is "
                    f"temporarily full (HTTP 402); {retrying}.")
                if attempt < attempts:
                    time.sleep(wait)
                continue
            # Out of credits or a request too large for the budget: retrying won't help.
            # A negative balance also blocks free models.
            hint = metadata.get("remedy_hint") or (
                "Your OpenRouter balance may be negative, which blocks free models too; add credits."
                if FREE_ROUTER in models or all(m.endswith(":free") for m in models)
                else f"Add credits, or add {FREE_ROUTER} as a fallback in the `model` input to stay free."
            )
            log("warning", f"OpenRouter returned HTTP 402 (insufficient credits) for {', '.join(models)}. {hint} Detail: {detail}")
            break
        if exc.code == 400 and use_json_mode:
            use_json_mode = False
        log("warning", f"Attempt {attempt}/{attempts}: OpenRouter returned HTTP {exc.code}: {detail}")
    except Exception as exc:  # noqa: BLE001
        log("warning", f"Attempt {attempt}/{attempts}: {exc}")
    if attempt < attempts:
        time.sleep(min(5 * 2 ** (attempt - 1), 60))

# -------------------------------------------------------------- output
GITHUB_BODY_LIMIT = 125000

compare_link = f"**Full Changelog**: {server}/{repo}/compare/{previous_tag}...{tag}" if previous_tag else ""
if ai_notes:
    title = env("IN_TITLE_TEMPLATE", "{tag}: {title}").replace("{tag}", tag).replace("{title}", ai_title)
    notes = ai_notes
    # The model places breaking changes itself; only report flagged commits it didn't mention.
    unmentioned = [sha for sha, _, _ in breaking_changes if sha not in ai_notes]
    if unmentioned:
        log("warning", f"The model's notes don't mention flagged breaking commit(s) {', '.join(unmentioned)} by hash.")
    if compare_link and env_bool("IN_APPEND_CHANGELOG_LINK"):
        notes += f"\n\n{compare_link}"
else:
    if env_bool("IN_FAIL_ON_ERROR"):
        sys.exit("::error::Could not generate release notes with OpenRouter.")
    log("warning", "Could not generate release notes with OpenRouter; using fallback notes.")
    title = tag
    if github_notes:
        notes = github_notes
    else:
        notes = "## What's Changed\n" + "\n".join(line.splitlines()[0] for line in commit_lines)
        if compare_link and env_bool("IN_APPEND_CHANGELOG_LINK"):
            notes += f"\n\n{compare_link}"
    if breaking_text:
        notes = f"### ⚠️ Breaking Changes\n{breaking_text}\n\n{notes}"

if len(notes) >= GITHUB_BODY_LIMIT:  # the notes file adds a trailing newline
    # GitHub rejects release bodies over 125,000 characters. Breaking changes come first, so they survive.
    link = compare_link if compare_link and env_bool("IN_APPEND_CHANGELOG_LINK") else ""
    note = "\n\n_Release notes truncated to fit GitHub's size limit._" + (f"\n\n{link}" if link else "")
    notes = notes[: GITHUB_BODY_LIMIT - 1 - len(note)].rsplit("\n", 1)[0] + note
    log("warning", "Release notes exceeded GitHub's 125,000-character limit and were truncated.")

# A file per run: a job may call the action more than once and read each notes-file later.
fd, notes_file = tempfile.mkstemp(prefix="release-notes-", suffix=".md", dir=env("RUNNER_TEMP") or None)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write(notes + "\n")

set_output("title", title)
set_output("notes", notes)
set_output("notes-file", notes_file)
set_output("tag", tag)
set_output("previous-tag", previous_tag)
set_output("head-sha", head_sha)
set_output("model", used_model if ai_notes else "")
set_output("ai-generated", "true" if ai_notes else "false")

if env("GITHUB_STEP_SUMMARY"):
    source = f"`{used_model}` via OpenRouter" if ai_notes else "fallback (AI generation failed)"
    with open(env("GITHUB_STEP_SUMMARY"), "a", encoding="utf-8") as fh:
        fh.write(f"# {title}\n\n{notes}\n\n---\n_Generated by {source}._\n")
