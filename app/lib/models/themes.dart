import 'package:flutter/material.dart';

/// #RRGGBB → Farbe, sonst null.
Color? hexColor(Object? v) {
  if (v is! String || !RegExp(r'^#[0-9A-Fa-f]{6}$').hasMatch(v)) return null;
  return Color(0xFF000000 | int.parse(v.substring(1), radix: 16));
}

/// Farbschema vom Server (`/api/themes`). Mitgelieferte und von Admins installierte.
class ThemeSpec {
  final String id;
  final String name;
  final bool builtin;
  final Map<String, String> colors; // #RRGGBB, vom Server geprüft
  final Map<String, dynamic> style; // Designsprache (Hintergrund, Karten, Navigation …), vom Server geprüft
  /// Weitere Fassungen: 'light' und/oder 'dark', je mit vollständigen Farben und Stil (vom Server ergänzt).
  final Map<String, ThemeSpec> variants;

  const ThemeSpec({
    required this.id,
    required this.name,
    this.builtin = true,
    required this.colors,
    this.style = const {},
    this.variants = const {},
  });

  factory ThemeSpec.fromJson(Map<String, dynamic> json) {
    final id = (json['id'] as String?) ?? '';
    final name = (json['name'] as String?) ?? '';
    final builtin = json['builtin'] != false;
    Map<String, String> colorsOf(Object? raw) =>
        ((raw as Map?) ?? const {}).map((k, v) => MapEntry(k.toString(), v.toString()));
    return ThemeSpec(
      id: id,
      name: name,
      builtin: builtin,
      colors: colorsOf(json['colors']),
      style: (json['style'] as Map?)?.cast<String, dynamic>() ?? const {},
      variants: {
        for (final e in ((json['variants'] as Map?) ?? const {}).entries)
          if (e.key == 'light' || e.key == 'dark')
            e.key.toString(): ThemeSpec(
              id: id,
              name: name,
              builtin: builtin,
              colors: colorsOf((e.value as Map?)?['colors']),
              style: ((e.value as Map?)?['style'] as Map?)?.cast<String, dynamic>() ?? const {},
            ),
      },
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id, 'name': name, 'builtin': builtin, 'colors': colors, 'style': style,
        if (variants.isNotEmpty)
          'variants': {for (final e in variants.entries) e.key: {'colors': e.value.colors, 'style': e.value.style}},
      };

  /// Hell oder dunkel – aus der Hintergrundfarbe der Grundfassung.
  Brightness get brightness =>
      ThemeData.estimateBrightnessForColor(color('background') ?? const Color(0xFF000000));

  /// Gibt es beide Fassungen (Grundfassung + die andere)?
  bool get hasBothModes {
    final other = brightness == Brightness.dark ? 'light' : 'dark';
    return variants[other]?.usable ?? false;
  }

  /// Fassung für [wanted]; ohne passende Variante bleibt es bei der Grundfassung.
  ThemeSpec forBrightness(Brightness wanted) {
    if (brightness == wanted) return this;
    final v = variants[wanted == Brightness.dark ? 'dark' : 'light'];
    return v != null && v.usable ? v : this;
  }

  /// Farbe zu [key] oder null, wenn sie fehlt oder kein #RRGGBB ist.
  Color? color(String key) => hexColor(colors[key]);

  /// Vollständig genug, um daraus ein Theme zu bauen.
  bool get usable =>
      const ['primary', 'secondary', 'background', 'surface', 'surfaceHigh', 'border'].every((k) => color(k) != null);
}

/// Plugin in den Admin-Einstellungen (`/api/admin/settings`).
class AdminPlugin {
  final String id;
  final String name;
  final String description;
  final bool configured;
  final bool disabled;
  final bool active;
  final List<AdminField> fields;

  const AdminPlugin({
    required this.id,
    required this.name,
    this.description = '',
    this.configured = false,
    this.disabled = false,
    this.active = false,
    this.fields = const [],
  });

  factory AdminPlugin.fromJson(Map<String, dynamic> json) => AdminPlugin(
        id: (json['id'] as String?) ?? '',
        name: (json['name'] as String?) ?? '',
        description: (json['description'] as String?) ?? '',
        configured: json['configured'] == true,
        disabled: json['disabled'] == true,
        active: json['active'] == true,
        fields: ((json['fields'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(AdminField.fromJson)
            .toList(),
      );
}

class AdminField {
  final String key;
  final String label;
  final bool secret;
  final bool required;
  final String help;
  final String value; // bei Geheimnissen immer leer
  final bool isSet;

  const AdminField({
    required this.key,
    required this.label,
    this.secret = false,
    this.required = false,
    this.help = '',
    this.value = '',
    this.isSet = false,
  });

  factory AdminField.fromJson(Map<String, dynamic> json) => AdminField(
        key: (json['key'] as String?) ?? '',
        label: (json['label'] as String?) ?? '',
        secret: json['secret'] == true,
        required: json['required'] == true,
        help: (json['help'] as String?) ?? '',
        value: (json['value'] as String?) ?? '',
        isSet: json['is_set'] == true,
      );
}
