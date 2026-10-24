import 'package:flutter/material.dart';

/// A line of a plugin card: the text and an optional second, muted part.
class PluginCardLine {
  final String text;
  final String? secondary;
  const PluginCardLine(this.text, [this.secondary]);
}

/// One picture of a swipeable plugin card, with an optional caption and link of its own.
class PluginCardSlide {
  final String image;
  final String? caption;
  final String? secondary;
  final String? link;
  const PluginCardSlide(this.image, {this.caption, this.secondary, this.link});
}

/// A card a plugin adds to "Today" (`plugin_cards` of `GET /api/today`). The server has validated and shortened
/// everything; the image is a hub path below `/api/plugins/<id>/` that is loaded with the login.
class PluginCardData {
  /// Layout id: `plugin:<plugin id>:<card id>`.
  final String key;
  final String plugin;
  final String pluginName;
  final String title;
  final String icon;
  final List<PluginCardLine> lines;
  final String? image;
  final String? link;
  final String? badge;

  /// Two or more pictures are shown as one swipeable card instead of [image].
  final List<PluginCardSlide> slides;

  const PluginCardData({
    required this.key,
    required this.title,
    this.plugin = '',
    this.pluginName = '',
    this.icon = 'extension',
    this.lines = const [],
    this.image,
    this.link,
    this.badge,
    this.slides = const [],
  });

  factory PluginCardData.fromJson(Map<String, dynamic> json) {
    String? text(Object? v) => v is String && v.trim().isNotEmpty ? v : null;
    final rawLines = json['lines'];
    final rawSlides = json['slides'];
    return PluginCardData(
      key: text(json['key']) ?? '',
      plugin: text(json['plugin']) ?? '',
      pluginName: text(json['plugin_name']) ?? '',
      title: text(json['title']) ?? '',
      icon: text(json['icon']) ?? 'extension',
      lines: [
        if (rawLines is List)
          for (final l in rawLines.whereType<Map>())
            if (text(l['text']) != null) PluginCardLine(l['text'] as String, text(l['secondary'])),
      ],
      image: text(json['image']),
      link: text(json['link']),
      badge: text(json['badge']),
      slides: [
        if (rawSlides is List)
          for (final s in rawSlides.whereType<Map>())
            if (text(s['image']) != null)
              PluginCardSlide(s['image'] as String,
                  caption: text(s['caption']), secondary: text(s['secondary']), link: text(s['link'])),
      ],
    );
  }

  static List<PluginCardData> listFromJson(Object? raw) => [
        if (raw is List)
          for (final c in raw.whereType<Map>())
            if (c['key'] is String && (c['key'] as String).startsWith('plugin:'))
              PluginCardData.fromJson(Map<String, dynamic>.from(c)),
      ];
}

/// The Material icons a plugin card may use: the allow-list of the server (`app/plugins/hooks.py`).
const pluginCardIcons = <String, IconData>{
  'extension': Icons.extension_outlined,
  'info': Icons.info_outline,
  'event': Icons.event_outlined,
  'schedule': Icons.schedule,
  'check_circle': Icons.check_circle_outline,
  'shopping_cart': Icons.shopping_cart_outlined,
  'restaurant': Icons.restaurant_outlined,
  'home': Icons.home_outlined,
  'school': Icons.school_outlined,
  'sports_soccer': Icons.sports_soccer,
  'local_shipping': Icons.local_shipping_outlined,
  'cloud': Icons.cloud_outlined,
  'wb_sunny': Icons.wb_sunny_outlined,
  'notifications': Icons.notifications_none,
  'favorite': Icons.favorite_border,
  'star': Icons.star_border,
  'book': Icons.menu_book_outlined,
  'movie': Icons.movie_outlined,
  'music_note': Icons.music_note,
  'directions_car': Icons.directions_car_outlined,
  'directions_bus': Icons.directions_bus_outlined,
  'pets': Icons.pets,
  'build': Icons.build_outlined,
  'eco': Icons.eco_outlined,
  'water_drop': Icons.water_drop_outlined,
  'bolt': Icons.bolt,
  'lock': Icons.lock_outline,
  'payments': Icons.payments_outlined,
  'medication': Icons.medication_outlined,
  'cake': Icons.cake_outlined,
  'child_care': Icons.child_care,
  'fitness_center': Icons.fitness_center,
  'local_laundry_service': Icons.local_laundry_service_outlined,
  'delete_outline': Icons.delete_outline,
  'wifi': Icons.wifi,
  'thermostat': Icons.thermostat,
  'photo': Icons.photo_outlined,
  'celebration': Icons.celebration_outlined,
  'sync': Icons.sync,
  'warning': Icons.warning_amber_rounded,
};

IconData pluginCardIcon(String name) => pluginCardIcons[name] ?? Icons.extension_outlined;

/// Is this a layout id of a plugin card (`plugin:<plugin id>:<card id>`)?
bool isPluginCardId(String id) => id.startsWith('plugin:') && id.split(':').length == 3;

/// Reward action a parent can attach to a reward (`GET /api/stars/reward-actions`).
class RewardActionParam {
  final String key;
  final String label;
  final String type; // text | number | bool | select
  final bool required;
  final String? defaultValue;
  final String help;
  final List<(String, String)> options; // (value, label)
  const RewardActionParam({
    required this.key,
    required this.label,
    this.type = 'text',
    this.required = true,
    this.defaultValue,
    this.help = '',
    this.options = const [],
  });

  factory RewardActionParam.fromJson(Map<String, dynamic> j) => RewardActionParam(
        key: (j['key'] as String?) ?? '',
        label: (j['label'] as String?) ?? '',
        type: (j['type'] as String?) ?? 'text',
        required: j['required'] != false,
        defaultValue: j['default'] as String?,
        help: (j['help'] as String?) ?? '',
        options: [
          if (j['options'] is List)
            for (final o in (j['options'] as List).whereType<Map>()) ('${o['value']}', '${o['label'] ?? o['value']}'),
        ],
      );
}

class RewardActionChoice {
  final String plugin;
  final String pluginName;
  final String id;
  final String label;
  final List<RewardActionParam> params;
  const RewardActionChoice({
    required this.plugin,
    required this.pluginName,
    required this.id,
    required this.label,
    this.params = const [],
  });

  factory RewardActionChoice.fromJson(Map<String, dynamic> j) => RewardActionChoice(
        plugin: (j['plugin'] as String?) ?? '',
        pluginName: (j['plugin_name'] as String?) ?? (j['plugin'] as String?) ?? '',
        id: (j['id'] as String?) ?? '',
        label: (j['label'] as String?) ?? '',
        params: [
          if (j['params'] is List)
            for (final p in (j['params'] as List).whereType<Map>()) RewardActionParam.fromJson(Map<String, dynamic>.from(p)),
        ],
      );

  static List<RewardActionChoice> listFromJson(Object? raw) => [
        if (raw is Map && raw['items'] is List)
          for (final a in (raw['items'] as List).whereType<Map>()) RewardActionChoice.fromJson(Map<String, dynamic>.from(a)),
      ];
}

/// The action attached to a reward (parents only), with the parameter values.
class RewardActionRef {
  final String plugin;
  final String action;
  final Map<String, String> params;
  final String label;
  final String pluginName;
  final bool available; // false: the plugin is off or gone, the action cannot run right now
  const RewardActionRef({
    required this.plugin,
    required this.action,
    this.params = const {},
    this.label = '',
    this.pluginName = '',
    this.available = true,
  });

  static RewardActionRef? fromJson(Object? json) {
    if (json is! Map) return null;
    final params = json['params'];
    return RewardActionRef(
      plugin: (json['plugin'] as String?) ?? '',
      action: (json['action'] as String?) ?? '',
      params: params is Map ? {for (final e in params.entries) '${e.key}': '${e.value}'} : const {},
      label: (json['label'] as String?) ?? '',
      pluginName: (json['plugin_name'] as String?) ?? '',
      available: json['available'] != false,
    );
  }

  Map<String, dynamic> toJson() => {'plugin': plugin, 'action': action, 'params': params};
}

/// What a plugin action reported after a parent approved a reward.
class RewardActionResult {
  final bool ok;
  final String message;
  const RewardActionResult({required this.ok, required this.message});

  static RewardActionResult? fromJson(Object? json) => json is Map
      ? RewardActionResult(ok: json['ok'] == true, message: (json['message'] as String?) ?? '')
      : null;
}
