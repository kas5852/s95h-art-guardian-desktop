package io.github.kas5852.artguardian.buildrules;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

final class ShapeRulesTest {

    @Test
    void rejectsAnIfNestedInsideAnotherNestedIf(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Nested", classWithThreeNestedIfs());

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleMain");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("NestedIfDepth");
    }

    private static String classWithThreeNestedIfs() {
        return """
                package io.github.kas5852.artguardian;

                final class Nested {
                    private Nested() {}

                    static int pick(int first, int second, int third) {
                        if (first > 0) {
                            if (second > 0) {
                                if (third > 0) {
                                    return first;
                                }
                            }
                        }
                        return second;
                    }
                }
                """;
    }

    @Test
    void rejectsAMethodWithFiveParameters(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Adder", """
                package io.github.kas5852.artguardian;

                final class Adder {
                    private Adder() {}

                    static int add(int first, int second, int third, int fourth, int fifth) {
                        return first + second + third + fourth + fifth;
                    }
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleMain");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("ParameterNumber");
    }

    @Test
    void rejectsAMethodLongerThanTwentyLines(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Counter", counterWithStatements(21));

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleMain");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("MethodLength");
    }

    @Test
    void rejectsAnUnnamedNumber(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Window", """
                package io.github.kas5852.artguardian;

                final class Window {
                    private Window() {}

                    static boolean isLongEnough(int seconds) {
                        return seconds >= 1200;
                    }
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleMain");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("MagicNumber");
    }

    @Test
    void rejectsCatchingEveryException(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Careless", classThatCatchesEveryException());

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleMain");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("IllegalCatch");
    }

    private static String classThatCatchesEveryException() {
        return """
                package io.github.kas5852.artguardian;

                final class Careless {
                    private Careless() {}

                    static String run(Runnable work) {
                        try {
                            work.run();
                            return "ran";
                        } catch (Exception failure) {
                            return failure.getClass().getSimpleName();
                        }
                    }
                }
                """;
    }

    private static String counterWithStatements(int statements) {
        return """
                package io.github.kas5852.artguardian;

                final class Counter {
                    private Counter() {}

                    static int count() {
                        var total = 0;
                %s        return total;
                    }
                }
                """.formatted("        total++;\n".repeat(statements));
    }
}
