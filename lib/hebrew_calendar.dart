// lib/hebrew_calendar.dart

class HebrewDate {
  final int year;
  final int month;
  final int day;

  HebrewDate(this.year, this.month, this.day);

  static const List<String> _monthNames = [
    'Nisan', 'Iyar', 'Sivan', 'Tammuz', 'Av', 'Elul',
    'Tishrei', 'Cheshvan', 'Kislev', 'Tevet', 'Shevat', 'Adar', 'Adar II'
  ];

  static HebrewDate fromGregorian(DateTime date) {
    final jd = _gregorianToJD(date.year, date.month, date.day);
    return _jdToHebrew(jd);
  }

  String get monthName => _monthNames[month - 1];

  static int _gregorianToJD(int year, int month, int day) {
    final a = ((14 - month) / 12).floor();
    final y = year + 4800 - a;
    final m = month + 12 * a - 3;
    return day + ((153 * m + 2) / 5).floor() + 365 * y + (y / 4).floor() - (y / 100).floor() + (y / 400).floor() - 32045;
  }

  static HebrewDate _jdToHebrew(int jd) {
    // Very simplified approximation of Hebrew date — NOT halachically accurate
    final approx = DateTime.fromMillisecondsSinceEpoch((jd - 2440588) * 86400000);
    return HebrewDate(approx.year, (approx.month % 13) + 1, approx.day);
  }
}
