// lib/hebrew_calendar.dart

/// Accurate Hebrew calendar port from convertdate.hebrew
/// Includes full logic for molad, Rosh Hashanah delay, and month lengths
import 'package:flutter/material.dart';

class HebrewDate {
  final int year;
  final int month;
  final int day;

  HebrewDate(this.year, this.month, this.day);

  static const List<String> _monthNames = [
    'Nisan', 'Iyar', 'Sivan', 'Tammuz', 'Av', 'Elul',
    'Tishrei', 'Cheshvan', 'Kislev', 'Tevet', 'Shevat', 'Adar', 'Adar II'
  ];

  String get monthName => _monthNames[month - 1];

  static const double HEBREW_EPOCH = -1373429.0;

  static HebrewDate fromGregorian(DateTime date) {
    final jd = _gregorianToJD(date.year, date.month, date.day);
    return _jdToHebrew(jd);
  }

  static int _gregorianToJD(int year, int month, int day) {
    final a = ((14 - month) ~/ 12);
    final y = year + 4800 - a;
    final m = month + 12 * a - 3;
    return day + ((153 * m + 2) ~/ 5) + 365 * y + (y ~/ 4) - (y ~/ 100) + (y ~/ 400) - 32045;
  }

  static HebrewDate _jdToHebrew(int jd) {
    int year = (jd - 347995).toInt() ~/ 366 + 1;
    while (jd >= _roshHashanah(year + 1)) year++;
    int month = 1;
    while (jd > _toJD(year, month, lastDayOfHebrewMonth(year, month))) {
      month++;
    }
    int day = jd - _toJD(year, month, 1) + 1;
    return HebrewDate(year, month, day);
  }

  static double _toJD(int year, int month, int day) {
    int jd = _roshHashanah(year);
    for (int m = 1; m < month; m++) {
      jd += lastDayOfHebrewMonth(year, m);
    }
    return jd + day - 1;
  }

  static int lastDayOfHebrewMonth(int year, int month) {
    if ([1, 5, 7, 11, 12].contains(month)) return 30;
    if ([4, 6, 10, 13].contains(month)) return 29;
    if (month == 2) return isLongCheshvan(year) ? 30 : 29;
    if (month == 3) return isShortKislev(year) ? 29 : 30;
    if (month == 8) return isLeapYear(year) ? 30 : 29;
    return 29;
  }

  static bool isLongCheshvan(int year) => daysInYear(year) % 10 == 5;
  static bool isShortKislev(int year) => daysInYear(year) % 10 == 3;

  static int daysInYear(int year) => _roshHashanah(year + 1) - _roshHashanah(year);

  static int _roshHashanah(int year) {
    final monthsElapsed = ((235 * ((year - 1) ~/ 19)) + (12 * ((year - 1) % 19)) + (((7 * ((year - 1) % 19) + 1) ~/ 19))).toInt();
    final partsElapsed = 204 + 793 * (monthsElapsed % 1080);
    final hoursElapsed = 5 + 12 * monthsElapsed + (793 * (monthsElapsed ~/ 1080)) + (partsElapsed ~/ 1080);
    final day = 1 + 29 * monthsElapsed + (hoursElapsed ~/ 24);
    final parts = 1080 * (hoursElapsed % 24) + (partsElapsed % 1080);

    int roshHashanah = (HEBREW_EPOCH + day).floor();
    if (parts >= 19440 ||
        ((roshHashanah % 7) == 2 && parts >= 9924 && !isLeapYear(year)) ||
        ((roshHashanah % 7) == 1 && parts >= 16789 && isLeapYear(year - 1))) {
      roshHashanah += 1;
    }
    if ([0, 3, 5].contains(roshHashanah % 7)) {
      roshHashanah += 1;
    }
    return roshHashanah;
  }

  static bool isLeapYear(int year) => ((7 * year + 1) % 19) < 7;

  /// Identify major holidays based on Hebrew date
  String? get holiday {
    final m = month;
    final d = day;

    if ((m == 7 && (d == 1 || d == 2))) return 'Rosh Hashanah';
    if (m == 7 && d == 10) return 'Yom Kippur';
    if (m == 7 && d >= 15 && d <= 21) return 'Sukkot';
    if (m == 7 && d == 22) return 'Shemini Atzeret';
    if (m == 7 && d == 23) return 'Simchat Torah';
    if (m == 9 && d >= 25) return 'Hanukkah';
    if (m == 10 && d <= 2) return 'Hanukkah';
    if (m == 10 && d == 15) return 'Tu BiShvat';
    if ((m == 12 || m == 13) && d == 14) return 'Purim';
    if (m == 1 && d >= 15 && d <= 21) return 'Passover';
    if (m == 3 && d == 6) return 'Shavuot';
    if (m == 8 && d == 27) return 'Yom HaShoah';
    if (m == 8 && d == 4) return 'Yom HaZikaron';
    if (m == 8 && d == 5) return 'Yom HaAtzmaut';
    if (m == 9 && d == 28) return 'Yom Yerushalayim';

    return null;
  }

  /// Return a date range for likely Gregorian match of a Hebrew date in current year
  static DateTimeRange gDateRangeForHebrewDate(int hMonth, int hDay) {
    final now = DateTime.now();
    final currentYear = now.year;
    DateTime? min;
    DateTime? max;

    for (int y = currentYear - 10; y <= currentYear + 10; y++) {
      try {
        final g = _gregorianFromHebrew(y, hMonth, hDay);
        if (min == null || g.isBefore(min)) min = g;
        if (max == null || g.isAfter(max)) max = g;
      } catch (_) {}
    }
    return DateTimeRange(start: min ?? now, end: max ?? now);
  }

  static DateTime _gregorianFromHebrew(int year, int month, int day) {
    final jd = _toJD(year, month, day).round();
    int l = jd + 68569;
    int n = (4 * l) ~/ 146097;
    l = l - (146097 * n + 3) ~/ 4;
    int i = (4000 * (l + 1)) ~/ 1461001;
    l = l - (1461 * i) ~/ 4 + 31;
    int j = (80 * l) ~/ 2447;
    int d = l - (2447 * j) ~/ 80;
    l = j ~/ 11;
    int m = j + 2 - (12 * l);
    int y = 100 * (n - 49) + i + l;
    return DateTime(y, m, d);
  }
}
