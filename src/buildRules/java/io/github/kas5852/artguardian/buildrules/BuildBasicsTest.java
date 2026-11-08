package io.github.kas5852.artguardian.buildrules;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

final class BuildBasicsTest {

    @Test
    void acceptsCleanCodeAndRunsEveryCheckOnIt(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Address", """
                package io.github.kas5852.artguardian;

                record Address(String value) {

                    private static final String EXAMPLE = "https://example.invalid//path /* text */";

                    static Address example() {
                        return new Address(EXAMPLE);
                    }
                }
                """);
        project.addTestClass("AddressTest", passingTest());

        var verdict = project.build();

        assertThat(verdict.failedTasks()).isEmpty();
        assertThat(verdict.tasksThatRanAndPassed())
                .contains(":spotlessJavaCheck", ":compileJava", ":checkstyleMain", ":checkstyleTest", ":test");
    }

    @Test
    void rejectsUnformattedCode(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Messy", """
                package io.github.kas5852.artguardian;
                final class Messy { private Messy(){}  static int  answer(){return 1;} }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":spotlessJavaCheck");
    }

    @Test
    void rejectsAFailingTest(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addTestClass("BrokenTest", """
                package io.github.kas5852.artguardian;

                import static org.assertj.core.api.Assertions.assertThat;

                import org.junit.jupiter.api.Test;

                final class BrokenTest {

                    @Test
                    void expectsTheImpossible() {
                        assertThat(1).isEqualTo(2);
                    }
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":test");
    }

    private static String passingTest() {
        return """
                package io.github.kas5852.artguardian;

                import static org.assertj.core.api.Assertions.assertThat;

                import org.junit.jupiter.api.Test;

                final class AddressTest {

                    @Test
                    void keepsSlashesInsideTextAsText() {
                        assertThat(Address.example().value()).contains("//", "/*");
                    }
                }
                """;
    }
}
