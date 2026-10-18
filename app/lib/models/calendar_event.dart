import 'common.dart';
import '../l10n/l10n.dart';

class CalendarEvent {
  final String title;
  final DateTime? start;
  final DateTime? end;
  final bool allDay;
  final String? location;
  final String? calendar;
  final String? color;

  const CalendarEvent({
    required this.title,
    this.start,
    this.end,
    this.allDay = false,
    this.location,
    this.calendar,
    this.color,
  });

  factory CalendarEvent.fromJson(Map<String, dynamic> json) {
    final allDay = json['all_day'] == true;
    DateTime? parse(Object? raw) => allDay ? parseDay(raw) : parseDate(raw);
    return CalendarEvent(
      title: (json['title'] as String?) ?? l10n.event,
      start: parse(json['start']),
      end: parse(json['end']),
      allDay: allDay,
      location: json['location'] as String?,
      calendar: json['calendar'] as String?,
      color: json['color'] as String?,
    );
  }
}
