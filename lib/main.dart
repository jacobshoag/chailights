import 'package:flutter/material.dart';
import 'package:photo_manager/photo_manager.dart';
import 'dart:typed_data';
import 'hebrew_calendar.dart';

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ChaiLights',
      theme: ThemeData(primarySwatch: Colors.indigo),
      home: const HebrewPhotoGallery(),
    );
  }
}

class HebrewPhotoGallery extends StatefulWidget {
  const HebrewPhotoGallery({super.key});

  @override
  State<HebrewPhotoGallery> createState() => _HebrewPhotoGalleryState();
}

class _HebrewPhotoGalleryState extends State<HebrewPhotoGallery> {
  Map<String, List<_PhotoData>> groupedByHebrewDate = {};
  late HebrewDate todayHebrew;

  @override
  void initState() {
    super.initState();
    todayHebrew = HebrewDate.fromGregorian(DateTime.now());
    _loadPhotosForHebrewDate(todayHebrew);
  }

  Future<void> _loadPhotosForHebrewDate(HebrewDate targetHebrew) async {
    final permission = await PhotoManager.requestPermissionExtend();
    if (!permission.isAuth) return;

    final range = HebrewDate.gDateRangeForHebrewDate(targetHebrew.month, targetHebrew.day);

    final albums = await PhotoManager.getAssetPathList(onlyAll: true);
    final recent = albums.first;
    final assets = await recent.getAssetListRange(start: 0, end: 10000);

    Map<String, List<_PhotoData>> grouped = {};

    for (var asset in assets) {
      final photoDate = asset.createDateTime;
      if (photoDate.isBefore(range.start) || photoDate.isAfter(range.end)) continue;

      final heb = HebrewDate.fromGregorian(photoDate);
      if (heb.day == targetHebrew.day && heb.month == targetHebrew.month) {
        final bytes = await asset.originBytes;
        final label = "${heb.day} ${heb.monthName} ${heb.year}";
        grouped.putIfAbsent(label, () => []).add(_PhotoData(bytes!, photoDate, heb));
      }
    }

    setState(() => groupedByHebrewDate = grouped);
  }

  void _showPhotoFullscreen(_PhotoData photo) {
    showDialog(
      context: context,
      builder: (_) => Dialog(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Image.memory(photo.bytes),
            Padding(
              padding: const EdgeInsets.all(8.0),
              child: Text(
                "📅 ${photo.heb.day} ${photo.heb.monthName} ${photo.heb.year}\n🗓 ${photo.gregorian.toLocal().toString().split(' ')[0]}\n🎉 ${photo.heb.holiday ?? ''}",
                textAlign: TextAlign.center,
              ),
            )
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ChaiLights – Hebrew Memories')),
      body: groupedByHebrewDate.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              children: groupedByHebrewDate.entries.map((entry) {
                return ExpansionTile(
                  title: Text(entry.key),
                  children: entry.value
                      .map((photo) => GestureDetector(
                            onTap: () => _showPhotoFullscreen(photo),
                            child: Image.memory(photo.bytes, height: 150),
                          ))
                      .toList(),
                );
              }).toList(),
            ),
    );
  }
}

class _PhotoData {
  final Uint8List bytes;
  final DateTime gregorian;
  final HebrewDate heb;

  _PhotoData(this.bytes, this.gregorian, this.heb);
}
