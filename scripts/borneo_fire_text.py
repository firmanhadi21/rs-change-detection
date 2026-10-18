"""Every word the Borneo pages put on screen, in English and Indonesian.

Kept out of borneo_fire_pages.py so that the layout code stays readable and
so that a translation can be reviewed as prose rather than hunted through
f-strings.

RULES FOR ADDING A STRING. Templates take named fields only, never
positional, because the two languages do not order their clauses the same
way -- Indonesian often needs the figure after the noun where English puts
it before. Anything measured stays a field; nothing is spelled out in one
language and computed in the other, or the two decks drift.

Proper nouns stay as they are. "KLHK Penunjukan Kawasan Hutan", "FAO GAUL",
"MODIS FIRMS" and "WDPA" are names, not phrases to translate, and the
Indonesian deck is read by people who know them in that form.
"""

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "id": ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
           "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
}

# The forest-function keys are DATA, fixed by borneo_hotspots_7d.py. These
# are how they are printed. The Indonesian side uses the terms the
# designations actually carry in law rather than a translation of the gloss.
FUNGSI = {
    "en": {
        "APL (non-forest estate)": "APL (non-forest estate)",
        "HPK (convertible production)": "HPK (convertible production)",
        "HP (production)": "HP (production)",
        "HPT (limited production)": "HPT (limited production)",
        "HL (protection forest)": "HL (protection forest)",
        "Conservation (KSA/KPA)": "Conservation (KSA/KPA)",
        "water": "water", "unclassified": "unclassified",
        "_MY": "Malaysia (no KLHK class)",
    },
    "id": {
        "APL (non-forest estate)": "APL (Area Penggunaan Lain)",
        "HPK (convertible production)": "HPK (hutan produksi konversi)",
        "HP (production)": "HP (hutan produksi)",
        "HPT (limited production)": "HPT (hutan produksi terbatas)",
        "HL (protection forest)": "HL (hutan lindung)",
        "Conservation (KSA/KPA)": "Konservasi (KSA/KPA)",
        "water": "perairan", "unclassified": "tidak terklasifikasi",
        "_MY": "Malaysia (di luar klasifikasi KLHK)",
    },
}

# WDPA designations, which arrive in English.
DESIG = {
    "National Park": "Taman Nasional",
    "Nature Reserve": "Cagar Alam",
    "Grand Forest Park": "Taman Hutan Raya",
    "Wildlife Reserve": "Suaka Margasatwa",
    "Nature Recreation Park": "Taman Wisata Alam",
    "Game Reserve": "Taman Buru",
    "Undesigned": "tanpa penetapan",
}

# Fractions in words, so the prose can never contradict the figure it sits
# beside. Thresholds are percentages, highest first.
SHARE = {
    "en": [(88, "Nearly all of"), (72, "Three quarters of"),
           (60, "Two thirds of"), (44, "Half"), (28, "A third of"),
           (12, "A fifth of"), (0, "A small share of")],
    "id": [(88, "Hampir seluruh"), (72, "Tiga perempat"),
           (60, "Dua pertiga"), (44, "Separuh"), (28, "Sepertiga"),
           (12, "Seperlima"), (0, "Sebagian kecil")],
}

T = {
"en": {
 # ---- chrome ----------------------------------------------------------
 "footer_src": "MODIS FIRMS · KLHK Penunjukan Kawasan Hutan · FAO GAUL 2015",
 "page": "page",

 # ---- page 1 ----------------------------------------------------------
 "p1_eyebrow": "MODIS FIRMS · {d0} to {d1}",
 "p1_title": "Titik Panas Borneo",
 "p1_sub": "Active-fire detections across the whole island — Kalimantan,\n"
           "Sarawak, Sabah, Labuan and Brunei — attributed to province and,\n"
           "on the Indonesian side, to the legal function of the land beneath.",
 "p1_kicker": "DETECTIONS IN SEVEN DAYS",
 "p1_idn": "Indonesia — Kalimantan",
 "p1_mys": "Malaysia — Sarawak + Sabah",
 "p1_brn": "Brunei Darussalam",
 "p1_share": "These seven days are {share}% of every hotspot detected\n"
             "on Borneo since 1 January.",
 "p1_estate": "{word} the Indonesian fires are inside the forest estate, "
              "and\n{protected} of them are in protection forest or "
              "conservation areas,\nwhere burning is not permitted under "
              "any licence.",

 # ---- page 2 ----------------------------------------------------------
 "p2_eyebrow": "page 2 · administrative boundary",
 "p2_title": "This is a Kalimantan event",
 "p2_sub_a": "{pct}% of the island's fires this week are on the "
             "Indonesian side. ",
 "p2_sub_b": "Sarawak and Sabah are not merely quieter — both run BELOW "
             "their own {years}-year medians for the season to date, while "
             "every Kalimantan province runs {lo} to {hi} times "
             "above.",
 "p2_sub_c": "Island-wide the season stands at {ratio}× the {years}-year "
             "median to this date.",
 "p2_xlabel": "hotspot detections, {span}",
 "p2_lead1": "{region} alone carries {pct}% of the island total",
 "p2_lead2": ", and {region} another {pct}%",
 "p2_silent": "{regions} recorded no detections at all in the window.",
 "p2_note": "Kalimantan Utara does not appear: FAO GAUL 2015 predates the "
            "province\ncreated in 2012, so its territory is counted inside "
            "Kalimantan Timur.",

 # ---- page 3 ----------------------------------------------------------
 "p3_eyebrow": "page 3 · forest function",
 "p3_title": "Whose land is burning",
 "p3_sub": "Indonesian detections placed on the KLHK Penunjukan Kawasan "
           "Hutan\ndesignation, ordered by how much legal protection the "
           "land carries.",
 "p3_weak": "WEAKEST PROTECTION",
 "p3_strong": "STRONGEST PROTECTION",
 "p3_quote": "{word} the Indonesian fires — {estate}, {estate_pct}% — "
             "are inside the forest estate rather than on land released for "
             "other use. {protected} of them ({prot_pct}%) are in "
             "protection forest or conservation areas, where burning is not "
             "permitted under any licence.",
 "p3_note": "Kawasan hutan is an Indonesian legal designation with no "
            "Malaysian or Bruneian\nequivalent, so Sarawak, Sabah, Labuan "
            "and Brunei are left unclassified here rather\nthan mapped onto "
            "a foreign scheme.",

 # ---- page 4 ----------------------------------------------------------
 "p4_eyebrow": "page 4 · named areas",
 "p4_title": "Which protected areas",
 "p4_sub": "The conservation detections from the previous page, joined to "
           "WDPA\nfor names. The counts are unchanged — only the labels are "
           "new.",
 "p4_lead": "of all conservation-area burning this week is inside\njust two "
            "national parks: {a} and {b}.",
 "p4_xlabel": "detections in the window",
 "p4_rate": "{desig} · {rate} per 1,000 km²",
 "p4_prov_head": "NAMES WDPA DOES NOT CORROBORATE",
 "p4_prov": "A further {n} detections fall in WDPA polygons with no "
            "government-reported area, no designation, or a name that does "
            "not belong to the ground they cover — {listed}. They are "
            "counted in the total and kept out of the ranking above.",
 "p4_n1_h": "The counts come from KLHK, not from WDPA.",
 "p4_n1_b": "Whether a detection is in a conservation area is decided by "
            "the same Penunjukan Kawasan Hutan layer as page 3, so the "
            "total here is page 3's total. WDPA supplies the name and "
            "nothing else. A detection is never added because WDPA covers "
            "it, nor dropped because WDPA does not.",
 "p4_n2_h": "Protection forest is absent on purpose.",
 "p4_n2_b": "All {hl} HL detections fall outside WDPA entirely. HL is a "
            "KLHK watershed category, not an IUCN protected area — the two "
            "registries describe different things, which is why no figure "
            "here is built from both.",
 "p4_n3_h": "Muara Angke is the clearest mislabelling.",
 "p4_n3_b": "WDPA places a 654 km² reserve of that name at 116.7°E, 0.18°N "
            "in East Kalimantan. The Muara Angke reserve is about 25 ha, in "
            "Jakarta. The polygon is real and the burning in it is real; "
            "the name is not evidence about either.",

 # ---- page 5 ----------------------------------------------------------
 "p5_eyebrow": "page 5 · location",
 "p5_title": "Where they are",
 "p5_sub": "Every detection in the window, over land, sea, international "
           "and\nprovincial boundaries, with the cities the clusters sit "
           "near.",
 "p5_scale": "200 km",

 # ---- page 6 ----------------------------------------------------------
 "p6_eyebrow": "page 6 · context",
 "p6_title": "The season so far",
 "p6_sub": "How this week sits against the {lo}–{hi} record, and how much\n"
           "a ranking taken at this point in the year is worth.",
 "p6_perday": "detections per day",
 "p6_cloud": "MODIS sees a place twice a day at best and cloud blocks it "
             "entirely. The dips are as likely to be cloud as calm.",
 "p6_card1": "total detections, same definition",
 "p6_card2_l": "VS {lo}–{hi} MEDIAN",
 "p6_card2_s": "median {median}",
 "p6_card3_l": "RANK IN {years} YEARS",
 "p6_card3_s": "to this date in the year",
 "p6_caveat_early": "2015 sat exactly at the median on 20 August, and "
                    "became the\ncatastrophe everyone remembers — because "
                    "its fires peaked in\nSeptember and October. An August "
                    "ranking systematically\nunderstates El Niño years and "
                    "cannot tell you how a season ends.",
 "p6_caveat_late": "Borneo's fires peak in September and October, so a "
                   "ranking cut\nhere has seen the worst of the season "
                   "rather than guessing at it.\nThat is what makes this "
                   "one worth reading: 2015 and 2019 are\nalready in the "
                   "record it is being measured against.",
 "p6_pointer": "Page 7 sets out the data and the method in full: every "
               "input, the\nquery that produced each figure, and what the "
               "counts do not mean.",

 # ---- page 7 ----------------------------------------------------------
 "p7_eyebrow": "page 7 · data and method",
 "p7_title": "How this was made",
 "p7_sub": "Three public datasets and a four-step chain, run end to end.\n"
           "The counts beside each step are this run's own.",
 "p7_inputs": "INPUTS",
 "p7_i1_n": "NASA FIRMS active fire",
 "p7_i1_s": "MODIS Terra + Aqua, 1 km, daily",
 "p7_i1_r": "via Google Earth Engine · the detections themselves",
 "p7_i2_n": "FAO GAUL 2015, level 1",
 "p7_i2_s": "administrative boundaries, all three countries",
 "p7_i2_r": "which province, and which country, each detection is in",
 "p7_i3_n": "KLHK Penunjukan Kawasan Hutan",
 "p7_i3_s": "1:250,000 (2019) · Indonesia only",
 "p7_i3_r": "the legal function of the land under each Indonesian detection",
 "p7_chain": "THE CHAIN, AND WHAT SURVIVED EACH STEP",
 "p7_s1_n": "Query FIRMS",
 "p7_s1_b": "over {w}°E, {s}°S–{n}°N, {d0} to {d1}, confidence ≥ {conf}",
 "p7_s1_c": "{n} detections",
 "p7_s2_n": "Join to administrative boundaries",
 "p7_s2_b": "point in polygon against GAUL level 1. Anything at sea or off "
            "the island is dropped, never snapped to the nearest unit",
 "p7_s2_c": "{kept} kept · {dropped} dropped",
 "p7_s3_n": "Join to forest function",
 "p7_s3_b": "point in polygon against {poly} kawasan polygons read over the "
            "fire extent. A point on a shared boundary is counted once, so "
            "the total is conserved",
 "p7_s3_c": "{n} attributed",
 "p7_s4_n": "Rebuild the whole record",
 "p7_s4_b": "the same definition for 1 Jan–{end} of every year from "
            "{start}, summed per region at 1 km",
 "p7_s4_c": "{n} this year",
 "p7_foot": "borneo_fire_payload.py folds the two runs together and refuses "
            "to write if they came from\ndifferent FIRMS vintages. This "
            "document is borneo_fire_pages.py.",
 "p7_not": "WHAT THESE NUMBERS ARE NOT",
 "p7_n1_h": "A detection is not a fire.",
 "p7_n1_b": "Each count is one 1 km pixel on one day — a pixel-day. A "
            "single fire burning a week across four pixels contributes 28. "
            "The quantity is comparable across regions and years, and "
            "nothing more is claimed of it.",
 "p7_n2_h": "Not comparable to BMKG or ASEAN figures.",
 "p7_n2_b": "Those use VIIRS at 375 m, which detects several times more "
            "hotspots for the same fires. Earth Engine carries no VIIRS "
            "active fire, so the trade is a lower count for a record that "
            "is consistent back to {start}.",
 "p7_n3_h": "Absence is not calm.",
 "p7_n3_b": "MODIS sees a place twice a day at best and cloud blocks it "
            "entirely. A quiet day in the chart may be a clouded one, and "
            "smoke over a fire front suppresses detection where it is "
            "thickest.",
 "p7_n4_h": "Kalimantan Utara is inside Kalimantan Timur.",
 "p7_n4_b": "GAUL 2015 predates the province created in 2012. The forest "
            "layer is Indonesian law and has no Malaysian or Bruneian "
            "equivalent, so Sabah, Sarawak, Labuan and Brunei carry no "
            "forest-function breakdown rather than a fabricated one.",
},

"id": {
 # ---- chrome ----------------------------------------------------------
 "footer_src": "MODIS FIRMS · KLHK Penunjukan Kawasan Hutan · FAO GAUL 2015",
 "page": "halaman",

 # ---- page 1 ----------------------------------------------------------
 "p1_eyebrow": "MODIS FIRMS · {d0} sampai {d1}",
 "p1_title": "Titik Panas Borneo",
 "p1_sub": "Deteksi api aktif di seluruh pulau — Kalimantan, Sarawak,\n"
           "Sabah, Labuan dan Brunei — ditautkan ke provinsi dan, di sisi\n"
           "Indonesia, ke fungsi hukum lahan di bawahnya.",
 "p1_kicker": "DETEKSI DALAM TUJUH HARI",
 "p1_idn": "Indonesia — Kalimantan",
 "p1_mys": "Malaysia — Sarawak + Sabah",
 "p1_brn": "Brunei Darussalam",
 "p1_share": "Tujuh hari ini adalah {share}% dari seluruh titik panas\n"
             "di Borneo sejak 1 Januari.",
 "p1_estate": "{word} kebakaran di Indonesia berada di dalam kawasan "
              "hutan,\ndan {protected} di antaranya di hutan lindung atau "
              "kawasan konservasi,\ntempat membakar tidak diizinkan oleh "
              "izin apa pun.",

 # ---- page 2 ----------------------------------------------------------
 "p2_eyebrow": "halaman 2 · batas administrasi",
 "p2_title": "Ini peristiwa Kalimantan",
 "p2_sub_a": "{pct}% kebakaran di pulau ini pekan ini berada di sisi "
             "Indonesia. ",
 "p2_sub_b": "Sarawak dan Sabah bukan sekadar lebih sepi — keduanya berada "
             "DI BAWAH median {years} tahun mereka sendiri untuk musim "
             "sampai hari ini, sementara setiap provinsi di Kalimantan "
             "berada {lo} sampai {hi} kali di atasnya.",
 "p2_sub_c": "Untuk seluruh pulau, musim ini berada pada {ratio}× "
             "median {years} tahun sampai tanggal ini.",
 "p2_xlabel": "deteksi titik panas, {span}",
 "p2_lead1": "{region} sendiri menyumbang {pct}% dari total pulau",
 "p2_lead2": ", dan {region} {pct}% lagi",
 "p2_silent": "{regions} sama sekali tidak mencatat deteksi dalam rentang "
              "ini.",
 "p2_note": "Kalimantan Utara tidak muncul: FAO GAUL 2015 mendahului "
            "provinsi yang\ndibentuk pada 2012, sehingga wilayahnya masih "
            "terhitung di dalam Kalimantan Timur.",

 # ---- page 3 ----------------------------------------------------------
 "p3_eyebrow": "halaman 3 · fungsi kawasan",
 "p3_title": "Lahan siapa yang terbakar",
 "p3_sub": "Deteksi di Indonesia ditempatkan pada penetapan KLHK "
           "Penunjukan\nKawasan Hutan, diurutkan menurut kekuatan "
           "perlindungan hukumnya.",
 "p3_weak": "PERLINDUNGAN TERLEMAH",
 "p3_strong": "PERLINDUNGAN TERKUAT",
 "p3_quote": "{word} kebakaran di Indonesia — {estate}, {estate_pct}% "
             "— berada di dalam kawasan hutan, bukan di lahan yang sudah "
             "dilepaskan untuk penggunaan lain. {protected} di antaranya "
             "({prot_pct}%) berada di hutan lindung atau kawasan "
             "konservasi, tempat membakar tidak diizinkan oleh izin apa pun.",
 "p3_note": "Kawasan hutan adalah penetapan hukum Indonesia yang tidak "
            "punya padanan di\nMalaysia maupun Brunei, sehingga Sarawak, "
            "Sabah, Labuan dan Brunei dibiarkan\ntanpa klasifikasi di sini "
            "alih-alih dipaksakan ke skema asing.",

 # ---- page 4 ----------------------------------------------------------
 "p4_eyebrow": "halaman 4 · kawasan bernama",
 "p4_title": "Kawasan lindung yang mana",
 "p4_sub": "Deteksi di kawasan konservasi dari halaman sebelumnya, "
           "ditautkan ke\nWDPA untuk namanya. Angkanya tidak berubah — "
           "hanya labelnya yang baru.",
 "p4_lead": "dari seluruh kebakaran kawasan konservasi pekan ini\nberada "
            "di dua taman nasional saja: {a} dan {b}.",
 "p4_xlabel": "deteksi dalam rentang ini",
 "p4_rate": "{desig} · {rate} per 1.000 km²",
 "p4_prov_head": "NAMA YANG TIDAK DIKUKUHKAN WDPA",
 "p4_prov": "Sebanyak {n} deteksi lagi jatuh di poligon WDPA yang tidak "
            "punya luas resmi dari pemerintah, tanpa penetapan, atau "
            "bernama tidak sesuai dengan lahan yang dicakupnya — {listed}. "
            "Semuanya tetap dihitung dalam total dan dikeluarkan dari "
            "peringkat di atas.",
 "p4_n1_h": "Angkanya berasal dari KLHK, bukan dari WDPA.",
 "p4_n1_b": "Apakah sebuah deteksi berada di kawasan konservasi ditentukan "
            "oleh lapisan Penunjukan Kawasan Hutan yang sama dengan halaman "
            "3, sehingga total di sini adalah total halaman 3. WDPA hanya "
            "memasok nama. Tidak ada deteksi yang ditambahkan karena WDPA "
            "mencakupnya, atau dibuang karena WDPA tidak mencakupnya.",
 "p4_n2_h": "Hutan lindung sengaja tidak ada di sini.",
 "p4_n2_b": "Seluruh {hl} deteksi HL jatuh di luar WDPA. HL adalah kategori "
            "tata air KLHK, bukan kawasan lindung IUCN — kedua pangkalan "
            "data ini menggambarkan hal yang berbeda, dan itulah sebabnya "
            "tidak ada satu angka pun di sini yang dibangun dari keduanya.",
 "p4_n3_h": "Muara Angke adalah kesalahan label yang paling jelas.",
 "p4_n3_b": "WDPA menempatkan cagar alam seluas 654 km² dengan nama itu di "
            "116,7°BT, 0,18°LU di Kalimantan Timur. Cagar Alam Muara Angke "
            "luasnya sekitar 25 ha, di Jakarta. Poligonnya nyata dan "
            "kebakaran di dalamnya nyata; namanya bukan bukti atas "
            "keduanya.",

 # ---- page 5 ----------------------------------------------------------
 "p5_eyebrow": "halaman 5 · lokasi",
 "p5_title": "Di mana letaknya",
 "p5_sub": "Setiap deteksi dalam rentang ini, di atas daratan, laut, batas\n"
           "negara dan batas provinsi, dengan kota-kota terdekat dari "
           "setiap gerombolan.",
 "p5_scale": "200 km",

 # ---- page 6 ----------------------------------------------------------
 "p6_eyebrow": "halaman 6 · konteks",
 "p6_title": "Musim ini sejauh ini",
 "p6_sub": "Bagaimana pekan ini dibandingkan dengan catatan {lo}–{hi}, dan\n"
           "seberapa berarti peringkat yang diambil pada titik tahun ini.",
 "p6_perday": "deteksi per hari",
 "p6_cloud": "MODIS paling banter melihat satu tempat dua kali sehari dan "
             "awan menutupnya sama sekali. Lembahnya bisa jadi awan, bukan "
             "reda.",
 "p6_card1": "total deteksi, definisi yang sama",
 "p6_card2_l": "DIBANDING MEDIAN {lo}–{hi}",
 "p6_card2_s": "median {median}",
 "p6_card3_l": "PERINGKAT DARI {years} TAHUN",
 "p6_card3_s": "sampai tanggal ini dalam setahun",
 "p6_caveat_early": "Pada 20 Agustus 2015 duduk tepat di median, lalu "
                    "menjadi\nbencana yang semua orang ingat — karena "
                    "kebakarannya memuncak\npada September dan Oktober. "
                    "Peringkat per Agustus secara sistematis\nmeremehkan "
                    "tahun El Niño dan tidak bisa memberi tahu akhir musim.",
 "p6_caveat_late": "Kebakaran di Borneo memuncak pada September dan "
                   "Oktober, jadi\nperingkat yang dipotong di sini sudah "
                   "melihat puncak musimnya,\nbukan menebaknya. Itulah yang "
                   "membuatnya layak dibaca: 2015 dan\n2019 sudah ada di "
                   "dalam catatan pembandingnya.",
 "p6_pointer": "Halaman 7 memuat data dan metodenya secara lengkap: setiap "
               "masukan,\nkueri yang menghasilkan tiap angka, dan apa yang "
               "bukan arti angka itu.",

 # ---- page 7 ----------------------------------------------------------
 "p7_eyebrow": "halaman 7 · data dan metode",
 "p7_title": "Bagaimana ini dibuat",
 "p7_sub": "Tiga pangkalan data publik dan rantai empat langkah, "
           "dijalankan utuh.\nAngka di samping tiap langkah berasal dari "
           "proses ini sendiri.",
 "p7_inputs": "MASUKAN",
 "p7_i1_n": "NASA FIRMS api aktif",
 "p7_i1_s": "MODIS Terra + Aqua, 1 km, harian",
 "p7_i1_r": "lewat Google Earth Engine · deteksinya sendiri",
 "p7_i2_n": "FAO GAUL 2015, level 1",
 "p7_i2_s": "batas administrasi, ketiga negara",
 "p7_i2_r": "provinsi dan negara tempat tiap deteksi berada",
 "p7_i3_n": "KLHK Penunjukan Kawasan Hutan",
 "p7_i3_s": "1:250.000 (2019) · hanya Indonesia",
 "p7_i3_r": "fungsi hukum lahan di bawah tiap deteksi di Indonesia",
 "p7_chain": "RANTAINYA, DAN APA YANG LOLOS DI TIAP LANGKAH",
 "p7_s1_n": "Kueri FIRMS",
 "p7_s1_b": "pada {w}°BT, {s}°LS–{n}°LU, {d0} sampai {d1}, "
            "confidence ≥ {conf}",
 "p7_s1_c": "{n} deteksi",
 "p7_s2_n": "Tautkan ke batas administrasi",
 "p7_s2_b": "titik dalam poligon terhadap GAUL level 1. Apa pun yang di "
            "laut atau di luar pulau dibuang, tidak pernah digeser ke unit "
            "terdekat",
 "p7_s2_c": "{kept} tersisa · {dropped} dibuang",
 "p7_s3_n": "Tautkan ke fungsi kawasan",
 "p7_s3_b": "titik dalam poligon terhadap {poly} poligon kawasan yang "
            "dibaca pada cakupan kebakaran. Titik di batas bersama dihitung "
            "sekali, sehingga totalnya terjaga",
 "p7_s3_c": "{n} tertautkan",
 "p7_s4_n": "Bangun ulang seluruh catatan",
 "p7_s4_b": "definisi yang sama untuk 1 Jan–{end} tiap tahun sejak "
            "{start}, dijumlahkan per wilayah pada 1 km",
 "p7_s4_c": "{n} tahun ini",
 "p7_foot": "borneo_fire_payload.py menyatukan kedua proses dan menolak "
            "menulis jika keduanya berasal\ndari vintage FIRMS yang "
            "berbeda. Dokumen ini adalah borneo_fire_pages.py.",
 "p7_not": "APA YANG BUKAN ARTI ANGKA INI",
 "p7_n1_h": "Satu deteksi bukan satu kebakaran.",
 "p7_n1_b": "Tiap hitungan adalah satu piksel 1 km pada satu hari — satu "
            "piksel-hari. Satu kebakaran yang menyala sepekan di empat "
            "piksel menyumbang 28. Besaran ini sebanding antarwilayah dan "
            "antartahun, dan tidak lebih dari itu yang diklaim.",
 "p7_n2_h": "Tidak sebanding dengan angka BMKG atau ASEAN.",
 "p7_n2_b": "Keduanya memakai VIIRS 375 m, yang mendeteksi beberapa kali "
            "lipat lebih banyak titik panas untuk kebakaran yang sama. "
            "Earth Engine tidak menyediakan VIIRS api aktif, jadi "
            "tukarannya adalah hitungan yang lebih rendah demi catatan yang "
            "konsisten sampai {start}.",
 "p7_n3_h": "Tidak terdeteksi bukan berarti reda.",
 "p7_n3_b": "MODIS paling banter melihat satu tempat dua kali sehari dan "
            "awan menutupnya sama sekali. Hari yang sepi di grafik bisa "
            "jadi hari yang berawan, dan asap di atas muka api menekan "
            "deteksi justru di tempat yang paling tebal.",
 "p7_n4_h": "Kalimantan Utara ada di dalam Kalimantan Timur.",
 "p7_n4_b": "GAUL 2015 mendahului provinsi yang dibentuk pada 2012. "
            "Lapisan kawasan hutan adalah hukum Indonesia dan tidak punya "
            "padanan di Malaysia maupun Brunei, sehingga Sabah, Sarawak, "
            "Labuan dan Brunei tidak memperoleh rincian fungsi kawasan "
            "alih-alih diberi rincian yang dikarang.",
},
}


def share_word(pct, lang):
    for cut, word in SHARE[lang]:
        if pct >= cut:
            return word
    return SHARE[lang][-1][1]


def ribuan(n, lang):
    """Thousands separator. Indonesian uses a full stop, English a comma."""
    s = f"{int(round(n)):,}"
    return s.replace(",", ".") if lang == "id" else s


def desimal(v, lang, d=1):
    s = f"{v:.{d}f}"
    return s.replace(".", ",") if lang == "id" else s
