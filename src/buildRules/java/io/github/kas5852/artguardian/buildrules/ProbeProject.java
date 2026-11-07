package io.github.kas5852.artguardian.buildrules;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import org.gradle.testkit.runner.GradleRunner;

final class ProbeProject {

    private static final Path REPOSITORY = Path.of(requiredProperty("artguardian.repository"));
    private static final Path TEST_KIT = Path.of(requiredProperty("artguardian.testKit"));
    private static final Path RUNNING_JDK = Path.of(requiredProperty("java.home"));
    private static final String PACKAGE_FOLDER = "io/github/kas5852/artguardian";
    private static final List<String> RULE_FILES = List.of(
            "build.gradle.kts",
            "settings.gradle.kts",
            "gradle.properties",
            ".java-version",
            "gradle/libs.versions.toml",
            "config/checkstyle/checkstyle.xml");

    private final Path folder;

    private ProbeProject(Path folder) {
        this.folder = folder;
    }

    static ProbeProject withTheRepositoryRulesIn(Path folder) throws IOException {
        for (var ruleFile : RULE_FILES) {
            var copy = folder.resolve(ruleFile);
            Files.createDirectories(copy.getParent());
            Files.copy(REPOSITORY.resolve(ruleFile), copy);
        }
        return new ProbeProject(folder);
    }

    void addMainClass(String className, String source) throws IOException {
        writeSource("main", className, source);
    }

    void addTestClass(String className, String source) throws IOException {
        writeSource("test", className, source);
    }

    BuildVerdict build() {
        var result = GradleRunner.create()
                .withProjectDir(folder.toFile())
                .withTestKitDir(TEST_KIT.toFile())
                .withArguments(
                        "build",
                        "--continue",
                        "-Porg.gradle.java.installations.paths=" + RUNNING_JDK,
                        "-Porg.gradle.java.installations.auto-download=false",
                        "--no-build-cache")
                .run();
        return new BuildVerdict(result);
    }

    private void writeSource(String sourceSet, String className, String source) throws IOException {
        var file = folder.resolve("src/" + sourceSet + "/java/" + PACKAGE_FOLDER + "/" + className + ".java");
        Files.createDirectories(file.getParent());
        Files.writeString(file, source);
    }

    private static String requiredProperty(String name) {
        return Objects.requireNonNull(System.getProperty(name), "Missing system property " + name);
    }
}
