part of 'api_client.dart';

/// What plugins offer every person: their own settings and the pages they serve (docs/plugins.md).
mixin PluginUserApi on ApiClientBase {
  Future<List<PersonalPlugin>> personalPlugins() async =>
      PersonalPlugin.listFromJson(await _send('GET', '/api/plugins/personal-settings'));

  /// Saves the sent values. A secret that stays empty keeps the stored one. Returns the form as it is now.
  Future<PersonalPlugin> savePersonalSettings(String pluginId, Map<String, String> values) async =>
      PersonalPlugin.fromJson(await _send('PUT', '/api/plugins/${Uri.encodeComponent(pluginId)}/personal-settings',
          body: {'values': values}) as Map<String, dynamic>);

  Future<ConnectionResult> testPersonalSettings(String pluginId, Map<String, String> values) async =>
      ConnectionResult.fromJson(await _send(
          'POST', '/api/plugins/${Uri.encodeComponent(pluginId)}/personal-settings/test',
          body: {'values': values}) as Map<String, dynamic>);

  Future<List<PluginPageInfo>> pluginPages() async => PluginPageInfo.listFromJson(await _send('GET', '/api/plugin-pages'));

  /// A fresh short-lived address of the page, ready to open in a browser (with the hub's address in front).
  Future<Uri> pluginPageLink(String pluginId, String pageId, {String path = ''}) async {
    final json = await _send(
        'POST', '/api/plugin-pages/${Uri.encodeComponent(pluginId)}/${Uri.encodeComponent(pageId)}/link',
        body: {'path': path}) as Map<String, dynamic>;
    final base = await store.baseUrl() ?? '';
    return Uri.parse('$base${json['url']}');
  }
}
