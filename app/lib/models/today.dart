import 'birthday.dart';
import 'calendar_event.dart';
import 'common.dart';
import 'task.dart';
import 'timetable.dart';
import '../l10n/l10n.dart';

class TodayMeal {
  final String source;
  final String title;
  const TodayMeal({required this.source, required this.title});

  factory TodayMeal.fromJson(Map<String, dynamic> json) => TodayMeal(
        source: (json['source'] as String?) ?? 'hub',
        title: (json['title'] as String?) ?? '',
      );
}

class TodayReminder {
  final int id;
  final String title;
  final DateTime? due;
  const TodayReminder({required this.id, required this.title, this.due});

  factory TodayReminder.fromJson(Map<String, dynamic> json) => TodayReminder(
        id: parseInt(json['id']) ?? 0,
        title: (json['title'] as String?) ?? '',
        due: parseDate(json['due']),
      );
}

class TodayHouseState {
  final String name;
  final String? state;
  final String? unit;
  final String? entity; // z. B. sensor.kinderzimmer (für Symbol und Zusammenführung mit der Steuerung)
  const TodayHouseState({required this.name, this.state, this.unit, this.entity});

  factory TodayHouseState.fromJson(Map<String, dynamic> json) => TodayHouseState(
        name: (json['name'] as String?) ?? (json['entity_id'] as String?) ?? '',
        state: json['state'] as String?,
        unit: json['unit'] as String?,
        entity: json['entity_id'] as String?,
      );

  String get displayValue => switch (state) {
        null => l10n.stateUnavailable,
        'on' => l10n.stateOn,
        'off' => l10n.stateOff,
        _ => unit == null || unit!.isEmpty ? state! : '$state $unit',
      };
}

class HouseControl extends TodayHouseState {
  final String entityId;
  final List<String> actions;
  final int? brightness;
  const HouseControl({required this.entityId, required super.name, super.state,
    this.actions = const [], this.brightness});

  factory HouseControl.fromJson(Map<String, dynamic> json) => HouseControl(
    entityId: json['entity_id'] as String,
    name: json['name'] as String,
    state: json['state'] as String?,
    actions: (json['actions'] as List).cast<String>(),
    brightness: json['brightness'] as int?,
  );
}

class TodayData {
  final DateTime date;
  final List<CalendarEvent> events;
  final SourceResult<Task> tasks;
  final List<TodayMeal> meals;
  final int shoppingOpen;
  final List<TodayReminder> reminders;
  final Map<String, dynamic>? weather;
  final int notificationsUnread;
  final SourceResult<TodayHouseState> house;
  final List<Birthday> birthdays;
  final List<TodayTimetableChild> timetable;

  const TodayData({
    required this.date,
    this.events = const [],
    this.tasks = const SourceResult(status: SourceStatus.ok),
    this.meals = const [],
    this.shoppingOpen = 0,
    this.reminders = const [],
    this.weather,
    this.notificationsUnread = 0,
    this.house = const SourceResult(status: SourceStatus.notConfigured),
    this.birthdays = const [],
    this.timetable = const [],
  });

  factory TodayData.fromJson(Map<String, dynamic> json) {
    List<Map<String, dynamic>> maps(Object? raw) =>
        raw is List ? raw.whereType<Map<String, dynamic>>().toList() : const [];
    final tasks = json['tasks'];
    final house = json['house'];
    return TodayData(
      date: parseDay(json['date']) ?? DateTime.now(),
      events: maps(json['events']).map(CalendarEvent.fromJson).toList(),
      tasks: tasks is Map<String, dynamic>
          ? SourceResult.fromJson(tasks, Task.fromJson)
          : const SourceResult(status: SourceStatus.unavailable),
      meals: maps(json['meals']).map(TodayMeal.fromJson).toList(),
      shoppingOpen: parseInt(json['shopping_open']) ?? 0,
      reminders: maps(json['reminders']).map(TodayReminder.fromJson).toList(),
      weather: json['weather'] is Map<String, dynamic>
          ? json['weather'] as Map<String, dynamic>
          : null,
      notificationsUnread: parseInt(json['notifications_unread']) ?? 0,
      birthdays: maps(json['birthdays']).map(Birthday.fromJson).toList(),
      house: house is Map<String, dynamic>
          ? SourceResult.fromJson(house, TodayHouseState.fromJson)
          : const SourceResult(status: SourceStatus.notConfigured),
      timetable: parseTodayTimetable(json['timetable']),
    );
  }
}
