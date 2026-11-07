package io.github.kas5852.artguardian.buildrules;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

final class CommentRulesTest {

    @Test
    void rejectsALineComment(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Explained", """
                package io.github.kas5852.artguardian;

                final class Explained {
                    // this sentence belongs in a name
                    private Explained() {}
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleMain");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("TodoComment");
    }

    @Test
    void rejectsABlockComment(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Explained", """
                package io.github.kas5852.artguardian;

                final class Explained {
                    /* this sentence belongs in a name */
                    private Explained() {}
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleMain");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("TodoComment");
    }

    @Test
    void rejectsJavadoc(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addMainClass("Explained", """
                package io.github.kas5852.artguardian;

                /** This sentence belongs in a name. */
                final class Explained {
                    private Explained() {}
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleMain");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("TodoComment");
    }

    @Test
    void rejectsACommentInTestCode(@TempDir Path folder) throws IOException {
        var project = ProbeProject.withTheRepositoryRulesIn(folder);
        project.addTestClass("ExplainedTest", """
                package io.github.kas5852.artguardian;

                import org.junit.jupiter.api.Test;

                final class ExplainedTest {

                    @Test
                    void passes() {
                        // this sentence belongs in the test name
                    }
                }
                """);

        var verdict = project.build();

        assertThat(verdict.failedTasks()).containsExactly(":checkstyleTest");
        assertThat(verdict.brokenCheckstyleRules()).containsExactly("TodoComment");
    }
}
