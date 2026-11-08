package io.github.kas5852.artguardian.buildrules;

import java.util.List;
import java.util.regex.MatchResult;
import java.util.regex.Pattern;
import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.BuildTask;
import org.gradle.testkit.runner.TaskOutcome;

record BuildVerdict(BuildResult result) {

    private static final Pattern CHECKSTYLE_VIOLATION =
            Pattern.compile("^\\[ant:checkstyle] \\[ERROR] .* \\[(\\w+)]$", Pattern.MULTILINE);
    private static final Pattern COMPILER_DIAGNOSTIC =
            Pattern.compile("^\\S+\\.java:\\d+: (?:error|warning): \\[(\\w+)]", Pattern.MULTILINE);

    List<String> failedTasks() {
        return tasksThat(TaskOutcome.FAILED);
    }

    List<String> tasksThatRanAndPassed() {
        return tasksThat(TaskOutcome.SUCCESS);
    }

    List<String> brokenCheckstyleRules() {
        return ruleNamesReportedAs(CHECKSTYLE_VIOLATION);
    }

    List<String> compilerComplaints() {
        return ruleNamesReportedAs(COMPILER_DIAGNOSTIC);
    }

    private List<String> tasksThat(TaskOutcome outcome) {
        return result.tasks(outcome).stream().map(BuildTask::getPath).toList();
    }

    private List<String> ruleNamesReportedAs(Pattern report) {
        return report.matcher(result.getOutput())
                .results()
                .map(BuildVerdict::ruleName)
                .toList();
    }

    private static String ruleName(MatchResult reportLine) {
        return reportLine.group(1);
    }
}
