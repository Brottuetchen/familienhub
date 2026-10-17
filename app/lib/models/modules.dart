/// Welche Bereiche der Server anbietet (Kern + aktive Plugins), aus `/api/modules`.
class AppModules {
  final Set<String> enabled;
  final Map<String, String> pluginFor;

  const AppModules({required this.enabled, this.pluginFor = const {}});

  /// Ohne Antwort vom Server: alles zeigen (die Bereiche melden selbst „nicht eingerichtet“).
  static const all = AppModules(enabled: {
    'today', 'reminders', 'meals', 'tasks', 'calendar', 'shopping', 'books', 'weather', 'meal_source',
  });

  bool has(String module) => enabled.contains(module);

  factory AppModules.fromJson(Map<String, dynamic> json) {
    final mods = (json['modules'] as Map?)?.cast<String, dynamic>() ?? const {};
    final enabled = <String>{};
    final plugins = <String, String>{};
    mods.forEach((key, value) {
      if (value is Map && value['enabled'] == true) {
        enabled.add(key);
        if (value['plugin'] is String) plugins[key] = value['plugin'] as String;
      }
    });
    return AppModules(enabled: enabled, pluginFor: plugins);
  }
}
