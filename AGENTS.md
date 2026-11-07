# S95H Art Guardian

A small controller that keeps a Samsung S95H TV showing Samsung Art. It repairs
the artwork timer when the TV resets it from `off` to `240`, and optionally puts
the TV in standby from 4 AM to 9 AM so the OLED panel can run its maintenance.
It controls real hardware in someone's home, so it is deliberately cautious:
an uncertain power command is never repeated, and an unclear state stops the
controller until a person looks.

## Where the code is

- `art_guardian/` is the working Python implementation. It is being replaced by
  Java. Fix bugs here, but do not add features.
- `src/main/java/io/github/kas5852/artguardian/` is where the Java version goes.
  It is empty until the port starts.
- `art_guardian/engine.py` is the pure decision logic. Port it first, because
  everything else depends on it and it has no I/O.
- `config/checkstyle/checkstyle.xml` holds the mechanical readability rules.
- `src/buildRules/` proves those rules work. Each test builds a throwaway project
  with this repository's real build files and one deliberately bad Java file,
  and checks that the build fails at exactly that rule. When you add or change a
  rule, add or update its test there.
- `scripts/ci_gate.py` decides the overall CI result. `tests/test_ci_gate.py`
  proves that a failed, cancelled, or skipped job turns it red.
- `examples/` holds configs with placeholders only. `private/` and `config.json`
  hold real tokens, addresses, and device identities, and are never committed.

## Commands

Java. Gradle provisions JDK 25 itself, so any JDK 17 or newer can start it.

```sh
./gradlew build
./gradlew test --tests 'io.github.kas5852.artguardian.GuardianTest'
./gradlew spotlessApply
./gradlew buildRules
```

`./gradlew build` includes `buildRules`, which takes about 40 seconds when the
rules have changed and is skipped when they have not.

Python, from the repository root:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/test_engine.py
.venv/bin/ruff check art_guardian tests scripts
```

## Definition of done

1. `./gradlew build` passes. It formats, compiles with Error Prone and NullAway,
   runs Checkstyle, and runs every test. Warnings fail the build.
2. The Python tests and ruff pass if anything under `art_guardian/` changed.
3. Every changed Java file has been read top to bottom against the readability
   rules below. `.claude/agents/java-reviewer.md` is the review checklist.
4. Behaviour changes are covered by a test that fails without the change.

## The readability standard

Code in this repository must read like a book. Someone should be able to read
a file from top to bottom, once, and understand what happens and why, without
jumping around and without a single comment. This is the most important rule
here and the one most often broken.

- **No comments of any kind.** No `//`, no `/* */`, no Javadoc, no TODOs, and no
  commented-out code. Checkstyle fails the build on any comment. When you want
  to write one, put the explanation in a name instead: extract a method, a
  variable, or a constant whose name says what the comment would have said.
- **Order members in reading order.** The public entry point comes first. Each
  private method follows the method that first calls it, so the file reads like
  a story told from the top down.
- **One idea per method, at one level of detail.** A method either tells the
  story by calling well-named steps, or does one low-level step. It never mixes
  the two. Checkstyle enforces at most 20 lines, 4 parameters, and one level
  of nested `if`.
- **Names are whole words from the problem.** Use `standbyDuration`, not `dur`;
  use `connection`, not `conn`. Use the language of the TV and its owner: art
  mode, standby, maintenance window, latch, recovery. Booleans read as yes/no
  questions, like `isLatched` or `hasQualifiedStandby`. Methods are verbs.
- **Guard clauses, not else chains.** Handle the exceptional case and return
  early, so the normal path stays on the left margin.
- **Types say what values mean.** Use `Duration` and `Instant`, never a bare
  `long` or `double`. Wrap identifiers in records like `TvIdentity` and
  `MacAddress`, and check them in the record's constructor. Model outcomes as
  sealed interfaces or enums, matched with `switch` expressions. Never use
  strings or flag combinations for outcomes.
- **No boolean flag parameters.** `send(command, true)` hides meaning. Write two
  methods with honest names.
- **Constants are named for their meaning.** Use
  `MAINTENANCE_WINDOW = Duration.ofMinutes(20)`, not `1200`.

What that looks like:

```java
public Decision observe(TvMode mode, Instant now) {
    if (isLatched()) {
        return new Decision.StayLatched(latchReason);
    }
    if (missedASampleBefore(now)) {
        forgetEverythingObservedBefore(now);
    }
    return switch (mode) {
        case ART, TV -> watchForStableViewing(mode, now);
        case STANDBY -> waitOutTheMaintenanceWindow(now);
        case UNKNOWN -> cancelAnyPendingRecovery(now);
    };
}
```

## Java conventions

- Java 25. Prefer records, sealed interfaces, pattern matching, switch
  expressions, and `var` where the type is obvious from the right-hand side.
- Everything is non-null unless it is marked `@Nullable` from
  `org.jspecify.annotations`. NullAway checks this when compiling. Prefer
  `Optional` return values over `@Nullable` returns.
- Make things immutable by default. Fields are `final`, collections come from
  `List.of` and `Map.copyOf`, and classes are `final` unless built to be
  extended.
- Catch the narrowest exception you can handle. Catching `Exception` is allowed
  only in `main` and the scheduler loop, the outer edges that must log and keep
  running. Mark those with `@SuppressWarnings("checkstyle:IllegalCatch")`. That
  is the only suppression you may add without asking.
- Use only the JDK for networking and files: `java.net.http.HttpClient`, its
  WebSocket support, `java.nio.file`, and `FileChannel` locks. Ask before adding
  any runtime dependency.
- Inject `java.time.Clock` into anything that reads the time, so tests control
  the time.
- Tests use JUnit Jupiter and AssertJ. A test's method name is a sentence that
  describes the behaviour, like `resumesArtAfterTwentyMinutesOfStandby`. Each
  test checks one behaviour. Separate arrange, act, and assert with blank lines.
  Use fabricated devices and reserved addresses like `192.0.2.10`; never a real
  TV or network.

## Safety rules this code must keep

These come from the Python version. The Java port must keep every one, with a
test for each.

- Write the record of a power or Art Mode command to disk, atomically, before
  sending it. After a restart, an in-flight record means "uncertain". Stop and
  alert; never resend.
- Never retry a command whose result is unknown. Read the state back instead.
- If the TV is being watched, leave it alone. Seeing TV viewing during a
  recovery stops the controller.
- Bind every setting change to the TV's model and `duid`. Refuse to act on a
  different device.
- Connect to private LAN IPv4 addresses only. Never follow redirects or use
  proxies.
- Never put tokens, URLs, addresses, or device identifiers in logs, errors, or
  diagnostics. Log the exception's type, not its message.

## Boundaries

- Do not weaken a check to get a green build. Ask first before you disable a
  Checkstyle rule, relax an Error Prone check, add `@SuppressWarnings`, or skip
  a test.
- Do not edit `gradlew`, `gradlew.bat`, or anything in `gradle/wrapper/` by
  hand. Change the Gradle version with
  `./gradlew wrapper --gradle-version X --gradle-distribution-sha256-sum Y`.
- In workflows, pin every action to a full commit SHA, set `permissions: {}` at
  the top, and grant each job only what it needs. Never use
  `pull_request_target`, and never put `${{ }}` expressions inside `run:`.
- Every job in `.github/workflows/ci.yml` must be listed in the `needs` of
  `all-checks-passed`. `tests/test_ci_gate.py` fails if one is missing. Never add
  `continue-on-error`.
- `.github/zizmor.yml` holds one exception: zizmor wants the new `$/` syntax for
  calling `codeql.yml`, but actionlint 1.7.12 rejects it. Switch to `$/` and
  delete the exception once actionlint supports it.
- Never commit `config.json`, `private/`, tokens, real IP or MAC addresses, or a
  real `duid`.
- Commit messages are one short line.
