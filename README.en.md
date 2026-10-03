# AlienQA

[中文](README.md) | [English](README.en.md)

**Find the parts of your product that only insiders find obvious.**

AlienQA simulates an external user who understands the relevant industry but is using your product for the first time. It explores pages in a browser, forms expectations before acting, and saves gaps between expectations and observed behavior as findings with screenshots and replay evidence.

It is an experimental local tool for independent developers working on QA, UX and product experience. It scans running web applications and produces HTML reports that you can read offline.

## What it looks for

- A save operation gives no feedback, leaving users unsure whether it succeeded.
- A control appears editable but does not change the page state.
- Information shown in one step contradicts the next step.
- JavaScript exceptions, HTTP 5xx responses and other technical signals.
- Behavior that follows the internal design but still confuses an external user.

These are examples of findings AlienQA tries to detect. Results depend on the exploration path and models. A behavior can deserve a place in the analysis report even if the team considers it intentional.

## How expectations work

An external user brings common conventions and industry knowledge, without knowing the team's internal answers. AlienQA forms expectations from information visible before the action and then observes the result. Source code and internal instructions help locate the target or investigate a finding afterward; they do not teach the expectation model the intended answer in advance.

The default configuration takes the union of two expectation samples: **a requirement proposed once is worth checking.** Duplicate requirements are merged with their sources preserved, and disagreements remain visible. All findings enter the analysis report, where you can decide whether to accept them. Engineering work prioritizes exploration, processing and evidence preservation; a limited action or time budget cannot guarantee that every problem is found.

## Using a coding assistant

AlienQA is built for use by LLM assistants. You can give this repository to an assistant with terminal and browser access and ask it to read the documentation, install AlienQA, configure model roles, run a scan and interpret the report. Provide the target URL, the features to explore and your call budget.

For example:

> Read this repository's README, install and run AlienQA, and use English for the interface and report. Use the model access I provide to test this application URL: … Focus on: … Call budget: … When finished, open the analysis report and explain the expectation gaps, explored scope and incomplete work.

The quick start below works for users and coding assistants. Complete account login or provide credentials locally when required.

## Quick start

You need Python 3.11+, access to suitable language and vision models, and a running web application. From the repository directory on macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e . -c requirements-dev.lock
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/browsers"
python -m playwright install chromium
python -m alienqa --language en --ui
```

Open `http://127.0.0.1:5000`:

1. Configure text and vision models on the settings page. The supplied configuration uses DeepSeek and Qwen. You can supply their credentials through `DEEPSEEK_API_KEY` and `DASHSCOPE_API_KEY`; see [config/config.yaml](config/config.yaml) for role configuration.
2. Enter the application URL, for example `http://localhost:3000`.
3. Select **Playwright Chromium** in the advanced scan inputs, matching the browser installed above. The default Chrome option requires Chrome to be installed separately.
4. Choose an action and time budget, start the scan, and review the findings and analysis report.

The tool fills forms, clicks controls and submits data. For a first run, use a local application or resettable test data. Start the development server for a React, Vue or Next.js application before entering its URL. AlienQA does not install frontend dependencies automatically.

### English and Chinese

AlienQA supports English and Chinese for the console, CLI messages, model output, review screens and reports. Chinese remains the default. Set the language explicitly:

```bash
python -m alienqa --language en --help
python -m alienqa --language en --ui
```

You can also set `language` in your model YAML:

```yaml
llm:
  language: en
  # Keep your provider and role configuration here.
```

Or use an environment variable:

```bash
export ALIENQA_LANGUAGE=en
```

CLI selection follows this order: `--language`, configuration file, `ALIENQA_LANGUAGE`, then Chinese. Scans use the current console language. The English / 中文 navigation switch changes the language for subsequent scans, and each run records the language used. Application text, source quotations, user notes and historical model output keep their original wording.

### Use an existing Codex login

AlienQA can reuse an existing ChatGPT login in the official local Codex CLI. Install the CLI and complete `codex login`, then launch:

```bash
python -m alienqa --config config/codex.yaml --language en --ui
```

The example configuration supplies separate prompts and image inputs for the model roles. Use models available to your account. Calls consume that account's allowance, and monetary cost may be unavailable. See the [Codex login provider notes](docs/engineering/codex-login-provider.md) for implementation details and limitations; these engineering notes are currently in Chinese.

### Command-line scans

Supply model credentials through environment variables. Add `--config PATH` to use another role configuration. Settings saved by the console do not automatically become the CLI configuration.

Scan a running application and generate an analysis report:

```bash
python -m alienqa --language en --url http://localhost:3000 --browser chromium --max-actions 10 --artifacts-dir artifacts/my-run
```

The report is saved to `artifacts/my-run/analysis.html`. Use a new directory for each scan. You can read the report immediately, before reviewing any findings.

For an application that requires authentication, log in manually and save a session first:

```bash
python -m alienqa --language en --login https://example.com --session-out config/session.json
python -m alienqa --language en --url https://example.com --browser chromium --storage-state config/session.json --artifacts-dir artifacts/private-run
```

Reopen existing results to save decisions and notes without scanning again:

```bash
python -m alienqa --language en --review-run artifacts/my-run
```

Source-assisted scans use `--project-root` together with the actual application URL. Use `--app` for the selected application in a repository containing multiple apps. `--unit` and `--instructions` help locate the area to explore:

```bash
python -m alienqa --language en --project-root /path/to/app --url http://localhost:3000 --browser chromium --unit "Account settings" --artifacts-dir artifacts/source-run
```

If needed, add `--start-command "npm run dev"`; AlienQA waits for the URL and stops the process on exit. `--serve DIRECTORY` supports local static pages with `--entry`, `--base-path` and optional `--spa-fallback`. `--replay artifacts/my-run/replay/ID.json` replays a saved package. See `python -m alienqa --language en --help` for all parameters and the [developer guide](docs/engineering/developer-guide.md) for source and replay details.

## Reading and exporting results

The analysis report includes technical failures, expectation gaps proposed by models, and explanations of stopped, failed or inconclusive work. Actions, screenshots and expectation sources help explain why an external user might find a behavior surprising. Zero findings means this exploration produced no findings.

In the offline HTML report, each finding is accepted by default. You can reject a finding and add a note. **Save this finding** or **Save all choices** stores your choices in the current browser. **Export decisions and notes** downloads JSON. **Generate final report** downloads HTML containing only the currently accepted findings and their notes. Exports use the current selections immediately, without a model call or a prior save.

The original analysis report retains every finding. Offline selections do not write back to `review.json` in the scan directory. Browser-local choices may not follow the HTML file when you copy it or open it in another browser.

In the local console or the page opened with `--review-run`, you can confirm, reject, mark a finding as by design, or skip it, and add notes. These decisions are saved to the run. **By-design findings remain in the analysis report.** If you explicitly select the `confirmed` report mode, the report is filtered by confirmed decisions saved in that run. The default report mode is `analysis`.

The run directory contains raw signals, screenshots, model usage records and replay packages. Screenshots are embedded in the report, so the HTML remains readable offline. Sessions and replay packages can contain authentication state; keep them locally. Reports can contain business data. Usage records distinguish known usage from unknown cost. Action and time budgets do not impose a hard monetary spending limit.

CLI exit codes are `0` for a completed scan or successful utility operation, `2` for an incomplete scan or argument error, `1` for a runtime error, and `130` for interruption. Saved scan progress is retained when interrupted.

## Current scope

AlienQA focuses on accessible web pages and DOM interaction in the main page. It supports URL input, saved sessions, some source assistance and static build outputs. Fixed mechanism fixtures cover React/Vite, Vue/Vite and Next.js; this does not establish coverage of every framework version or business workflow.

Complex iframes, Shadow DOM and long business workflows have limitations. The sampling-union contract has engineering regression coverage. Six bounded real-model scans of TodoMVC, IT-Tools and Memos exposed gaps in menu interaction, input selection and observation. See [open-source application testing](docs/engineering/open-source-applications.md) and [compatibility and release status](docs/engineering/compatibility-and-release.md) for the recorded methods and evidence.

## Documentation and license

This README covers the public English workflow. Historical engineering documents and experimental results retain their original language.

- [Developer guide](docs/engineering/developer-guide.md): architecture, testing, configuration and engineering documentation.
- [Project status](docs/engineering/project-status-2026-10-02.md): completed work, evidence boundaries and next priorities.
- [MVP engineering plans](docs/engineering/mvp-planbooks/README.md): feature plans and technical subplans.

AlienQA uses the [MIT License](LICENSE). Third-party dependencies and example projects retain their own licenses.
