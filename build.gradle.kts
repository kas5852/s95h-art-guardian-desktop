import net.ltgt.gradle.errorprone.errorprone
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

plugins {
    java
    checkstyle
    alias(libs.plugins.errorprone)
    alias(libs.plugins.spotless)
}

group = "io.github.kas5852"
version = "0.1.0-SNAPSHOT"

val rootPackage = "io.github.kas5852.artguardian"
val javaVersionFile = layout.projectDirectory.file(".java-version")
val javaVersion = providers.fileContents(javaVersionFile).asText.map(String::trim)

java {
    toolchain {
        languageVersion = javaVersion.map(JavaLanguageVersion::of)
    }
}

dependencies {
    implementation(libs.jspecify)

    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testRuntimeOnly(libs.junit.platform.launcher)

    errorprone(libs.errorprone.core)
    errorprone(libs.nullaway)
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.compilerArgs.addAll(listOf("-Xlint:all", "-Werror", "-parameters"))
    options.errorprone {
        error("NullAway")
        option("NullAway:AnnotatedPackages", rootPackage)
        option("NullAway:JSpecifyMode", "true")
    }
}

val repositoryFolder = layout.projectDirectory.asFile
val testKitFolder =
    layout.buildDirectory
        .dir("test-kit")
        .get()
        .asFile
val buildRuleFiles =
    files(
        "build.gradle.kts",
        "settings.gradle.kts",
        "gradle.properties",
        ".java-version",
        "gradle/libs.versions.toml",
        "gradle/wrapper/gradle-wrapper.properties",
        "config/checkstyle",
    )

testing {
    suites {
        register<JvmTestSuite>("buildRules") {
            useJUnitJupiter(libs.versions.junit)
            dependencies {
                implementation(gradleTestKit())
                implementation(libs.assertj.core)
            }
            targets.configureEach {
                testTask.configure {
                    inputs.files(buildRuleFiles).withPathSensitivity(PathSensitivity.RELATIVE)
                    systemProperty("artguardian.repository", repositoryFolder.absolutePath)
                    systemProperty("artguardian.testKit", testKitFolder.absolutePath)
                }
            }
        }
    }
}

tasks.check {
    dependsOn(testing.suites.named("buildRules"))
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    testLogging {
        events("failed")
        exceptionFormat = TestExceptionFormat.FULL
    }
}

checkstyle {
    toolVersion = libs.versions.checkstyle.get()
    configDirectory = layout.projectDirectory.dir("config/checkstyle")
    maxErrors = 0
    maxWarnings = 0
}

spotless {
    java {
        target("src/**/*.java")
        palantirJavaFormat(libs.versions.formatter.get())
        removeUnusedImports()
        forbidWildcardImports()
        trimTrailingWhitespace()
        endWithNewline()
    }
    kotlinGradle {
        target("*.gradle.kts")
        ktlint()
    }
}
