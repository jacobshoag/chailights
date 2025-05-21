// lib/main.dart
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
  Map<String, List<Uint8List>> groupedByHebrewDate = {};

  @override
  void initState() {
    super.initState();
    _loadPhotos();
  }

  Future<void> _loadPhotos() async {
    final permission = await PhotoManager.requestPermissionExtend();
    if (!permission.isAuth) return;

    final albums = await PhotoManager.getAssetPathList(onlyAll: true);
    final recent = albums.first;
    final assets = await recent.getAssetListPaged(page: 0, size: 100);

    Map<String, List<Uint8List>> grouped = {};

    for (var asset in assets) {
      final file = await asset.originBytes;
      final date = asset.createDateTime;

      final hebDate = HebrewDate.fromGregorian(date);
      final label = "${hebDate.day} ${hebDate.monthName} ${hebDate.year}";

      grouped.putIfAbsent(label, () => []).add(file!);
    }

    setState(() {
      groupedByHebrewDate = grouped;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ChaiLights – Hebrew Dates')),
      body: groupedByHebrewDate.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              children: groupedByHebrewDate.entries.map((entry) {
                return ExpansionTile(
                  title: Text(entry.key),
                  children: entry.value
                      .map((bytes) => Image.memory(bytes, height: 150))
                      .toList(),
                );
              }).toList(),
            ),
    );
  }
}
