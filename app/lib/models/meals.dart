import 'common.dart';

class MealEntry {
  final int? id;
  final String? uid;
  final String title;
  final String source; // hub | cookidoo
  final String? mealType;
  final String? description;

  /// Nur bei Cookidoo über das Plugin: Rezept-ID (zum Austragen/Einkaufen), Zeit, Bild, Link.
  final String? cookidooId;
  final int? minutes;
  final String? image;
  final String? url;

  const MealEntry({
    this.id,
    this.uid,
    required this.title,
    required this.source,
    this.mealType,
    this.description,
    this.cookidooId,
    this.minutes,
    this.image,
    this.url,
  });

  bool get isCookidoo => source == 'cookidoo';

  factory MealEntry.fromJson(Map<String, dynamic> json) => MealEntry(
        id: parseInt(json['id']),
        uid: json['uid'] as String?,
        title: (json['title'] as String?) ?? '',
        source: (json['source'] as String?) ?? 'hub',
        mealType: json['meal_type'] as String?,
        description: json['description'] as String?,
        cookidooId: json['cookidoo_id'] as String?,
        minutes: parseInt(json['minutes']),
        image: json['image'] as String?,
        url: json['url'] as String?,
      );
}

/// Treffer der Cookidoo-Rezeptsuche.
class CookidooRecipe {
  final String id;
  final String name;
  final String? thumbnail;
  final String? url;

  const CookidooRecipe({required this.id, required this.name, this.thumbnail, this.url});

  factory CookidooRecipe.fromJson(Map<String, dynamic> json) => CookidooRecipe(
        id: (json['id'] as String?) ?? '',
        name: (json['name'] as String?) ?? '',
        thumbnail: (json['thumbnail'] as String?) ?? json['image'] as String?,
        url: json['url'] as String?,
      );
}

class MealDay {
  final DateTime date;
  final List<MealEntry> entries;

  const MealDay({required this.date, this.entries = const []});

  factory MealDay.fromJson(Map<String, dynamic> json) => MealDay(
        date: parseDay(json['date'])!,
        entries: ((json['entries'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(MealEntry.fromJson)
            .toList(),
      );
}

class MealWeek {
  final SourceStatus status;
  final String? error;
  final List<MealDay> days;

  const MealWeek({required this.status, this.error, this.days = const []});

  factory MealWeek.fromJson(Map<String, dynamic> json) {
    final r = SourceResult.fromJson(json, MealDay.fromJson, key: 'days');
    return MealWeek(status: r.status, error: r.error, days: r.items);
  }
}

/// ISO-Woche als `YYYY-Www`, wie `/api/meals?week=` sie erwartet.
String isoWeekOf(DateTime day) {
  final d = DateTime.utc(day.year, day.month, day.day);
  final thursday = d.add(Duration(days: 4 - d.weekday));
  final jan1 = DateTime.utc(thursday.year, 1, 1);
  final week = 1 + thursday.difference(jan1).inDays ~/ 7;
  return '${thursday.year}-W${week.toString().padLeft(2, '0')}';
}

/// Montag der Woche von [day].
DateTime mondayOf(DateTime day) =>
    DateTime(day.year, day.month, day.day).subtract(Duration(days: day.weekday - 1));
