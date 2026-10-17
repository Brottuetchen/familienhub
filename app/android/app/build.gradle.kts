import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Firebase nur, wenn eine eigene google-services.json vorliegt (nicht im Repo).
// Ohne Datei baut die App trotzdem, Push ist dann aus.
if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}

// App-ID pro Installation wählbar: ./gradlew -PfamilienhubAppId=org.example.hub
// Muss zum Paketnamen in der google-services.json passen.
val familienhubAppId = (project.findProperty("familienhubAppId") as String?) ?: "de.familienhub.app"

// Release-Signatur aus einer Datei außerhalb des Repos (storeFile, storePassword, keyAlias, keyPassword):
//   ./gradlew -PfamilienhubSigning=/pfad/key.properties   oder   FAMILIENHUB_SIGNING=/pfad/key.properties
// Ohne Datei: Debug-Schlüssel (nur zum Ausprobieren; Updates brauchen immer denselben Schlüssel).
val signingFile = ((project.findProperty("familienhubSigning") as String?) ?: System.getenv("FAMILIENHUB_SIGNING"))
    ?.let { file(it) }
    ?.takeIf { it.exists() }
val signingProps = Properties().apply { signingFile?.inputStream()?.use { load(it) } }

android {
    namespace = "de.familienhub.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        // flutter_local_notifications braucht java.time auf älteren Android-Versionen
        isCoreLibraryDesugaringEnabled = true
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = familienhubAppId
        minSdk = flutter.minSdkVersion  // flutter_secure_storage requires 21+
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (signingFile != null) {
            create("release") {
                storeFile = file(signingProps.getProperty("storeFile"))
                storePassword = signingProps.getProperty("storePassword")
                keyAlias = signingProps.getProperty("keyAlias")
                keyPassword = signingProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName(if (signingFile != null) "release" else "debug")
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}
