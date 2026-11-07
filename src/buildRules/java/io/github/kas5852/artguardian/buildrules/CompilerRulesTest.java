package io.github.kas5852.artguardian.buildrules;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

final class CompilerRulesTest {

    @Test
    void rejectsReturningNullWithoutSayingSo(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Lookup", """
                package io.github.kas5852.artguardian;

                final class Lookup {
                    private Lookup() {}

                    static String name() {
                        return null;
                    }
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":compileJava");
        assertThat(verdict.compilerComplaints()).containsExactly("NullAway");
    }

    @Test
    void rejectsAnExceptionThatIsCreatedButNeverThrown(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Guard", """
                package io.github.kas5852.artguardian;

                final class Guard {
                    private Guard() {}

                    static void requirePositive(int value) {
                        if (value < 0) {
                            new IllegalArgumentException("negative");
                        }
                    }
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":compileJava");
        assertThat(verdict.compilerComplaints()).containsExactly("DeadException");
    }

    @Test
    void treatsACompilerWarningAsAnError(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Loose", """
                package io.github.kas5852.artguardian;

                import java.util.List;

                final class Loose {
                    private Loose() {}

                    static int size(List items) {
                        return items.size();
                    }
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":compileJava");
        assertThat(verdict.compilerComplaints()).containsExactly("rawtypes");
    }
}
