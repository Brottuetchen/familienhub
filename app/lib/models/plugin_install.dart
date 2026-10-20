// Installing plugins from GitHub (Administration → Plugins & access): what the server's
// `/api/plugins/*` endpoints return. Texts arrive in the app's language.

import 'admin.dart' show ConnectionResult;

/// One setting of the form that is generated from the plugin's manifest.
class PluginSettingSpec {
  final String key;
  final String label;
  final String help;
  final String type; // text | url | password | number | bool
  final bool secret;
  final bool required;
  final String? defaultValue;
  final String example;

  /// Current value of a plain setting (empty for secrets, they are never sent).
  final String value;

  /// Whether a value is already stored (an update keeps it when the field stays empty).
  final bool isSet;

  const PluginSettingSpec({
    required this.key,
    required this.label,
    this.help = '',
    this.type = 'text',
    this.secret = false,
    this.required = false,
    this.defaultValue,
    this.example = '',
    this.value = '',
    this.isSet = false,
  });

  factory PluginSettingSpec.fromJson(Map<String, dynamic> j) => PluginSettingSpec(
        key: j['key'] as String,
        label: (j['label'] as String?) ?? j['key'] as String,
        help: (j['help'] as String?) ?? '',
        type: (j['type'] as String?) ?? 'text',
        secret: j['secret'] == true,
        required: j['required'] == true,
        defaultValue: j['default'] as String?,
        example: (j['example'] as String?) ?? '',
        value: (j['value'] as String?) ?? '',
        isSet: j['is_set'] == true,
      );
}

/// Result of "inspect": the plugin at one exact commit, ready to be reviewed.
class PluginPreview {
  final String url; // the normalised link, kept for updates
  final String repoUrl;
  final String sha;
  final String shortSha;
  final String id;
  final String name;
  final String version;
  final String description;
  final String author;
  final String homepage;
  final String license;
  final List<String> hosts;
  final List<String> capabilities; // labels
  final List<PluginSettingSpec> settings;
  final String? installedVersion;
  final bool sameSha;
  final List<String> warnings;
  final bool installEnabled;

  const PluginPreview({
    required this.url,
    required this.repoUrl,
    required this.sha,
    required this.shortSha,
    required this.id,
    required this.name,
    required this.version,
    this.description = '',
    this.author = '',
    this.homepage = '',
    this.license = '',
    this.hosts = const [],
    this.capabilities = const [],
    this.settings = const [],
    this.installedVersion,
    this.sameSha = false,
    this.warnings = const [],
    this.installEnabled = true,
  });

  bool get isInstalled => installedVersion != null;

  factory PluginPreview.fromJson(Map<String, dynamic> j) {
    final m = (j['manifest'] as Map?)?.cast<String, dynamic>() ?? const {};
    final installed = (j['installed'] as Map?)?.cast<String, dynamic>();
    List<String> strings(Object? v) => ((v as List?) ?? const []).map((e) => '$e').toList();
    return PluginPreview(
      url: j['url'] as String,
      repoUrl: ((j['repo'] as Map?)?['url'] as String?) ?? j['url'] as String,
      sha: j['sha'] as String,
      shortSha: (j['short_sha'] as String?) ?? (j['sha'] as String).substring(0, 7),
      id: m['id'] as String,
      name: (m['name'] as String?) ?? m['id'] as String,
      version: (m['version'] as String?) ?? '',
      description: (m['description'] as String?) ?? '',
      author: (m['author'] as String?) ?? '',
      homepage: (m['homepage'] as String?) ?? '',
      license: (m['license'] as String?) ?? '',
      hosts: strings(m['hosts']),
      capabilities: [
        for (final c in (m['capabilities'] as List?) ?? const [])
          if (c is Map) (c['label'] as String?) ?? '${c['id']}' else '$c'
      ],
      settings: ((j['settings'] as List?) ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(PluginSettingSpec.fromJson)
          .toList(),
      installedVersion: installed?['version'] as String?,
      sameSha: installed?['same_sha'] == true,
      warnings: strings(j['warnings']),
      installEnabled: j['install_enabled'] != false,
    );
  }
}

/// A plugin that was installed from GitHub (`GET /api/plugins/installed`).
class InstalledPluginInfo {
  final String id;
  final String name;
  final String version;
  final String shortSha;
  final String repoUrl; // the link the admin pasted; used for updates
  final bool enabled;
  final bool loaded;
  final bool active;
  final String? error;

  const InstalledPluginInfo({
    required this.id,
    required this.name,
    required this.version,
    this.shortSha = '',
    this.repoUrl = '',
    this.enabled = true,
    this.loaded = false,
    this.active = false,
    this.error,
  });

  factory InstalledPluginInfo.fromJson(Map<String, dynamic> j) => InstalledPluginInfo(
        id: j['id'] as String,
        name: (j['name'] as String?) ?? j['id'] as String,
        version: (j['version'] as String?) ?? '',
        shortSha: (j['short_sha'] as String?) ?? '',
        repoUrl: (j['repo_url'] as String?) ?? '',
        enabled: j['enabled'] != false,
        loaded: j['loaded'] == true,
        active: j['active'] == true,
        error: j['error'] as String?,
      );
}

class PluginInstallState {
  final bool enabled; // false: the operator switched the installer off
  final List<InstalledPluginInfo> items;
  const PluginInstallState({this.enabled = true, this.items = const []});

  InstalledPluginInfo? byId(String id) {
    for (final p in items) {
      if (p.id == id) return p;
    }
    return null;
  }

  factory PluginInstallState.fromJson(Map<String, dynamic> j) => PluginInstallState(
        enabled: j['enabled'] != false,
        items: ((j['items'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(InstalledPluginInfo.fromJson)
            .toList(),
      );
}

class PluginInstallResult {
  final String id;
  final String version;
  final bool updated;
  final bool restartRequired;
  final bool active;

  /// The plugin's own connection test with the values just entered (null: the plugin has none).
  final ConnectionResult? connectionTest;
  const PluginInstallResult({
    required this.id,
    required this.version,
    this.updated = false,
    this.restartRequired = false,
    this.active = false,
    this.connectionTest,
  });

  factory PluginInstallResult.fromJson(Map<String, dynamic> j) => PluginInstallResult(
        id: j['id'] as String,
        version: (j['version'] as String?) ?? '',
        updated: j['updated'] == true,
        restartRequired: j['restart_required'] == true,
        active: j['active'] == true,
        connectionTest: j['connection_test'] is Map
            ? ConnectionResult.fromJson(Map<String, dynamic>.from(j['connection_test'] as Map))
            : null,
      );
}
