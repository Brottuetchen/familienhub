// Personal plugin settings and plugin pages: what `/api/plugins/personal-settings` and `/api/plugin-pages` return.

import 'plugin_install.dart' show PluginSettingSpec;

/// An active plugin with settings every person fills in for themselves (*More → My connections*).
class PersonalPlugin {
  final String id;
  final String name;
  final String description;
  final bool hasTest;
  final List<PluginSettingSpec> fields;

  const PersonalPlugin({
    required this.id,
    required this.name,
    this.description = '',
    this.hasTest = false,
    this.fields = const [],
  });

  /// True when a required field has no value yet (the connection still needs to be set up).
  bool get needsSetup => fields.any((f) => f.required && f.type != 'bool' && !(f.secret ? f.isSet : (f.value.isNotEmpty || f.isSet)));

  factory PersonalPlugin.fromJson(Map<String, dynamic> j) => PersonalPlugin(
        id: j['id'] as String,
        name: (j['name'] as String?) ?? j['id'] as String,
        description: (j['description'] as String?) ?? '',
        hasTest: j['has_test'] == true,
        fields: ((j['fields'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(PluginSettingSpec.fromJson)
            .toList(),
      );

  static List<PersonalPlugin> listFromJson(dynamic json) {
    final items = json is Map ? json['items'] : null;
    return [
      for (final e in (items is List ? items : const []))
        if (e is Map<String, dynamic> && e['id'] is String) PersonalPlugin.fromJson(e)
    ];
  }
}

/// A page a plugin serves (listed under *More*).
class PluginPageInfo {
  final String plugin;
  final String pluginName;
  final String id;
  final String title;
  final String icon;

  const PluginPageInfo({
    required this.plugin,
    required this.pluginName,
    required this.id,
    required this.title,
    this.icon = 'extension',
  });

  factory PluginPageInfo.fromJson(Map<String, dynamic> j) => PluginPageInfo(
        plugin: j['plugin'] as String,
        pluginName: (j['plugin_name'] as String?) ?? j['plugin'] as String,
        id: j['id'] as String,
        title: (j['title'] as String?) ?? j['id'] as String,
        icon: (j['icon'] as String?) ?? 'extension',
      );

  static List<PluginPageInfo> listFromJson(dynamic json) {
    final items = json is Map ? json['items'] : null;
    return [
      for (final e in (items is List ? items : const []))
        if (e is Map<String, dynamic> && e['plugin'] is String && e['id'] is String) PluginPageInfo.fromJson(e)
    ];
  }
}
