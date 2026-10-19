"""Every word of the West Sumatra burn-to-palm deck, English and Indonesian.

Same rules as borneo_fire_text.py: named fields only, numbers arrive
already formatted for the language, proper nouns stay as they are.

A note on register. This deck touches an allegation of illegal land
conversion, so the Indonesian is written at the same careful distance as
the English -- "berada di" rather than "diubah menjadi", association
rather than cause -- because a translation that sharpens the claim is
not a translation.
"""

# KLHK designations as the deck prints them.
STATUS = {
    "en": {
        "AREA PENGGUNAAN LAIN": "APL · released land",
        "HUTAN PRODUKSI KONVERSI": "HPK · convertible production",
        "HUTAN PRODUKSI": "HP · production",
        "HUTAN PRODUKSI TERBATAS": "HPT · limited production",
        "HUTAN LINDUNG": "HL · protection forest",
        "LAUT/AIR": "water",
        "CAGAR ALAM": "nature reserve",
        "TAMAN NASIONAL": "national park",
        "SUAKA MARGASATWA": "wildlife reserve",
    },
    "id": {
        "AREA PENGGUNAAN LAIN": "APL · Area Penggunaan Lain",
        "HUTAN PRODUKSI KONVERSI": "HPK · hutan produksi konversi",
        "HUTAN PRODUKSI": "HP · hutan produksi",
        "HUTAN PRODUKSI TERBATAS": "HPT · hutan produksi terbatas",
        "HUTAN LINDUNG": "HL · hutan lindung",
        "LAUT/AIR": "perairan",
        "CAGAR ALAM": "cagar alam",
        "TAMAN NASIONAL": "taman nasional",
        "SUAKA MARGASATWA": "suaka margasatwa",
    },
}

T = {
"en": {
 "src": "MODIS MCD64A1 · Descals et al. global oil palm · "
        "KLHK Penunjukan Kawasan Hutan",

 # ---- 1 cover ------------------------------------------------------
 "p1_eyebrow": "west sumatra · burns of {y0}–{y1}",
 "p1_title": "Burnt, then planted",
 "p1_sub": "Land in West Sumatra that burned between {y0} and {y1} and now\n"
           "carries oil palm planted after the fire. Not whether it "
           "happens —\nwhere, and under which land status.",
 "p1_strict": "HP + HPT + HL · WHERE IT IS NOT",
 "p1_kicker": "HECTARES BURNT, THEN PLANTED WITH PALM",
 "p1_of": "{pct}% of all land that burned in the period",
 "p1_lead": "The pattern is real and large. It is also, almost\n"
            "everywhere, entirely lawful.",
 "p1_note": "Oil palm on released land is ordinary agriculture. The "
            "question this deck\nasks is what is left once that is set "
            "aside.",

 # ---- 2 by status --------------------------------------------------
 "p2_eyebrow": "page 2 · land status",
 "p2_title": "Where it is allowed",
 "p2_sub": "The same burnt hectares, split by what KLHK says the land is.\n"
           "Ordered by how much legal protection it carries.",
 "p2_xlabel": "share of burnt land now carrying palm planted after the fire",
 "p2_quote": "Of {estate} ha inside the forest estate, {hpk} ha is HPK — "
             "convertible production forest, which is designated for "
             "conversion. The pattern tracks permission almost exactly.",
 "p2_note": "Burnt hectares per class are printed beside each bar. A high "
            "share on a\nsmall class is a small number of hectares.",

 # ---- 3 timing -----------------------------------------------------
 "p3_eyebrow": "page 3 · timing",
 "p3_title": "The year after the fire",
 "p3_sub": "Years between a cell burning and the palm on it being planted.\n"
           "Only cells where planting came after the fire are counted.",
 "p3_ylabel": "cells",
 "p3_xlabel": "years from fire to planting",
 "p3_quote": "Median {median} years, and the single commonest gap is one. "
             "{n1} of {ntot} cells were planted the year after they burned. "
             "Topography does not produce that.",
 "p3_note": "This is the strongest evidence here that the fire and the "
            "planting are one\nevent rather than two things that happen in "
            "the same kind of place. It is\nstill association, not intent.",

 # ---- 4 sites ------------------------------------------------------
 "p4_eyebrow": "page 4 · the residue",
 "p4_title": "What does not explain away",
 "p4_sub": "Contiguous sites of {minha} ha or more inside the forest "
           "estate.\nEach one can be checked against the gazette for that "
           "parcel.",
 "p4_cols": ("longitude", "latitude", "ha", "burnt", "planted", "status"),
 "p4_hl": "{n} ha of this sits in HUTAN LINDUNG — protection forest, "
          "where conversion is not permitted under any licence.",
 "p4_note": "Forest-estate boundaries move. A parcel inside today's HL may "
            "have been\nreleased when it was planted, and only the gazette "
            "settles that. These are\nplaces to check, not findings.",

 # ---- 5 the 2026 case ----------------------------------------------
 "p5_eyebrow": "page 5 · dharmasraya, september 2026",
 "p5_title": "The case in the news",
 "p5_sub": "Police in Dharmasraya reported about 5.9 ha of recently burnt\n"
           "limited-production forest found planted with oil palm "
           "seedlings.",
 "p5_found": "WHAT THE SATELLITES INDEPENDENTLY CONFIRM",
 "p5_f1": "A fire on 15 September 2026",
 "p5_f1b": "the date given in the report",
 "p5_f2": "Inside HUTAN PRODUKSI TERBATAS",
 "p5_f2b": "the designation given in the report",
 "p5_f3": "101.549°E, 0.903°S, Dharmasraya",
 "p5_f3b": "the only HPT fire in the regency that month",
 "p5_cant": "WHAT THEY CANNOT SHOW",
 "p5_c1": "That the seedlings are oil palm, or that they are seedlings. A "
          "month-old palm is a few centimetres of frond at 9 m spacing. "
          "Nothing in orbit resolves it.",
 "p5_c2": "The planting at all. 5.9 ha is a tenth of one MCD64A1 pixel, "
          "and between 20 September and 19 October no Sentinel-2 scene "
          "over the regency was under 40% cloud.",
 "p5_c3": "Anything about the earlier figures. This deck's statistics stop "
          "at 2018 burns; this case is 2026 and is not in them.",
 "p5_close": "The patrol finding seedlings on the ground is better evidence "
             "than any image could be. What orbit adds is that the fire "
             "they describe is there, on that date, on that land status.",

 # ---- 6 method -----------------------------------------------------
 "p6_eyebrow": "page 6 · data and method",
 "p6_title": "How this was made",
 "p6_sub": "Three public datasets on one {scale} m grid, and four limits\n"
           "that bound what any of it can mean.",
 "p6_inputs": "INPUTS",
 "p6_i1": "MODIS MCD64A1 burned area",
 "p6_i1s": "500 m, monthly · earliest year each cell burned, {y0}–{y1}",
 "p6_i2": "Descals et al. global oil palm",
 "p6_i2s": "10 m · classes 1 industrial and 2 smallholder, with a "
           "planting_year band",
 "p6_i3": "KLHK Penunjukan Kawasan Hutan",
 "p6_i3s": "1:250,000 (2019) · the legal status of every parcel",
 "p6_rule": "THE TEST",
 "p6_rule_b": "A cell counts when it burned in year Y and carries palm "
              "whose planting_year is strictly greater than Y. Strictly, "
              "so palm already standing when the fire passed is not read "
              "as a consequence of it. Burns stop at {y1} because planting "
              "is observed to {py}, giving every burn at least three years "
              "to show a plantation.",
 "p6_not": "FOUR THINGS THIS DOES NOT ESTABLISH",
 "p6_n1_h": "Intent.",
 "p6_n1_b": "Observational data does not separate burning in order to "
            "plant from clearing by fire on land already destined for "
            "planting, nor either from both following on from flat, "
            "drained, accessible ground. The one-year lag bears on this. "
            "It does not settle it.",
 "p6_n2_h": "Illegality.",
 "p6_n2_b": "Forest-estate boundaries move, and releases and swaps happen. "
            "A cell inside today's HPT may have been released land when "
            "the palm went in. Only the gazette for that parcel settles "
            "it.",
 "p6_n3_h": "Small clearing — and this is the big one.",
 "p6_n3_b": "MCD64A1 is 500 m and cannot see a burn of a few hectares. "
            "That is the scale the Dharmasraya case operates at and "
            "probably most of the pathway. The near-zero HPT figure on "
            "page 2 is a statement about what the sensor resolves, not "
            "about what happens.",
 "p6_n4_h": "Which fire.",
 "p6_n4_b": "A cell that burned more than once is credited to its first "
            "burn, so a later re-burn before planting is invisible here.",
},

"id": {
 "src": "MODIS MCD64A1 · Peta sawit global Descals dkk. · "
        "KLHK Penunjukan Kawasan Hutan",

 # ---- 1 cover ------------------------------------------------------
 "p1_eyebrow": "sumatera barat · kebakaran {y0}–{y1}",
 "p1_title": "Terbakar, lalu ditanami",
 "p1_sub": "Lahan di Sumatera Barat yang terbakar antara {y0} dan {y1}\n"
           "dan kini bersawit yang ditanam setelah kebakaran. Bukan "
           "apakah ini\nterjadi — melainkan di mana, dan pada status "
           "lahan apa.",
 "p1_strict": "HP + HPT + HL · TEMPAT YANG TIDAK DIIZINKAN",
 "p1_kicker": "HEKTARE TERBAKAR, LALU DITANAMI SAWIT",
 "p1_of": "{pct}% dari seluruh lahan yang terbakar pada periode itu",
 "p1_lead": "Polanya nyata dan luas. Dan hampir seluruhnya,\n"
            "juga sah menurut hukum.",
 "p1_note": "Sawit di lahan yang sudah dilepaskan adalah pertanian biasa. "
            "Yang ditanyakan\npaparan ini adalah apa yang tersisa setelah "
            "itu dikesampingkan.",

 # ---- 2 by status --------------------------------------------------
 "p2_eyebrow": "halaman 2 · status lahan",
 "p2_title": "Di mana hal itu diizinkan",
 "p2_sub": "Hektare terbakar yang sama, dipilah menurut status lahan "
           "versi KLHK.\nDiurutkan menurut kekuatan perlindungan "
           "hukumnya.",
 "p2_xlabel": "bagian lahan terbakar yang kini bersawit, ditanam setelah "
              "kebakaran",
 "p2_quote": "Dari {estate} ha di dalam kawasan hutan, {hpk} ha adalah "
             "HPK — hutan produksi konversi, yang memang diperuntukkan "
             "bagi konversi. Polanya mengikuti izin hampir persis.",
 "p2_note": "Hektare terbakar tiap kelas dicetak di samping batangnya. "
            "Persentase besar pada\nkelas kecil berarti hektare yang "
            "sedikit.",

 # ---- 3 timing -----------------------------------------------------
 "p3_eyebrow": "halaman 3 · waktu",
 "p3_title": "Setahun setelah api",
 "p3_sub": "Jarak tahun antara sebuah sel terbakar dan sawit di atasnya "
           "ditanam.\nHanya sel yang penanamannya setelah kebakaran yang "
           "dihitung.",
 "p3_ylabel": "sel",
 "p3_xlabel": "tahun dari kebakaran ke penanaman",
 "p3_quote": "Median {median} tahun, dan jarak yang paling sering muncul "
             "adalah satu tahun. {n1} dari {ntot} sel ditanami pada tahun "
             "setelah terbakar. Bentang alam tidak menghasilkan pola itu.",
 "p3_note": "Inilah bukti terkuat di sini bahwa kebakaran dan penanaman "
            "adalah satu\nperistiwa, bukan dua hal yang kebetulan terjadi "
            "di jenis tempat yang sama.\nIni tetap asosiasi, bukan niat.",

 # ---- 4 sites ------------------------------------------------------
 "p4_eyebrow": "halaman 4 · sisanya",
 "p4_title": "Yang tidak mudah dijelaskan",
 "p4_sub": "Lokasi menyatu seluas {minha} ha atau lebih di dalam kawasan "
           "hutan.\nMasing-masing dapat diperiksa terhadap SK untuk "
           "bidang itu.",
 "p4_cols": ("bujur", "lintang", "ha", "terbakar", "ditanam", "status"),
 "p4_hl": "{n} ha di antaranya berada di HUTAN LINDUNG — tempat konversi "
          "tidak diizinkan oleh izin apa pun.",
 "p4_note": "Batas kawasan hutan berubah. Bidang yang kini di dalam HL "
            "bisa saja sudah\ndilepaskan ketika ditanami, dan hanya SK "
            "yang memastikannya. Ini tempat\nuntuk diperiksa, bukan "
            "kesimpulan.",

 # ---- 5 the 2026 case ----------------------------------------------
 "p5_eyebrow": "halaman 5 · dharmasraya, september 2026",
 "p5_title": "Kasus yang diberitakan",
 "p5_sub": "Polisi di Dharmasraya melaporkan sekitar 5,9 ha bekas "
           "kebakaran\ndi hutan produksi terbatas yang ditemukan sudah "
           "ditanami bibit sawit.",
 "p5_found": "YANG DIKUKUHKAN SATELIT SECARA TERPISAH",
 "p5_f1": "Kebakaran pada 15 September 2026",
 "p5_f1b": "tanggal yang disebut dalam berita",
 "p5_f2": "Di dalam HUTAN PRODUKSI TERBATAS",
 "p5_f2b": "status lahan yang disebut dalam berita",
 "p5_f3": "101,549°BT, 0,903°LS, Dharmasraya",
 "p5_f3b": "satu-satunya kebakaran HPT di kabupaten itu bulan tersebut",
 "p5_cant": "YANG TIDAK BISA DITUNJUKKAN SATELIT",
 "p5_c1": "Bahwa bibitnya adalah sawit, atau bahwa itu bibit. Sawit "
          "berumur sebulan hanyalah beberapa sentimeter pelepah dengan "
          "jarak tanam 9 m. Tidak ada wahana di orbit yang bisa "
          "memisahkannya.",
 "p5_c2": "Penanamannya sama sekali. 5,9 ha adalah sepersepuluh satu "
          "piksel MCD64A1, dan antara 20 September dan 19 Oktober tidak "
          "ada satu pun citra Sentinel-2 di kabupaten itu dengan awan di "
          "bawah 40%.",
 "p5_c3": "Apa pun tentang angka-angka sebelumnya. Statistik paparan ini "
          "berhenti pada kebakaran 2018; kasus ini 2026 dan tidak "
          "termasuk di dalamnya.",
 "p5_close": "Temuan patroli di lapangan adalah bukti yang lebih kuat "
             "daripada citra mana pun. Yang ditambahkan orbit adalah "
             "bahwa kebakaran yang mereka sebut memang ada, pada tanggal "
             "itu, pada status lahan itu.",

 # ---- 6 method -----------------------------------------------------
 "p6_eyebrow": "halaman 6 · data dan metode",
 "p6_title": "Bagaimana ini dibuat",
 "p6_sub": "Tiga pangkalan data publik pada satu grid {scale} m, dan "
           "empat batas\nyang membingkai arti semuanya.",
 "p6_inputs": "MASUKAN",
 "p6_i1": "MODIS MCD64A1 area terbakar",
 "p6_i1s": "500 m, bulanan · tahun terawal tiap sel terbakar, {y0}–{y1}",
 "p6_i2": "Peta sawit global Descals dkk.",
 "p6_i2s": "10 m · kelas 1 industri dan 2 rakyat, dengan kanal "
           "planting_year",
 "p6_i3": "KLHK Penunjukan Kawasan Hutan",
 "p6_i3s": "1:250.000 (2019) · status hukum tiap bidang",
 "p6_rule": "UJINYA",
 "p6_rule_b": "Sebuah sel dihitung bila terbakar pada tahun Y dan "
              "bersawit yang planting_year-nya lebih besar dari Y. Harus "
              "lebih besar, agar sawit yang sudah berdiri saat api lewat "
              "tidak dibaca sebagai akibatnya. Kebakaran berhenti di "
              "{y1} karena penanaman teramati sampai {py}, sehingga tiap "
              "kebakaran punya sedikitnya tiga tahun untuk memperlihatkan "
              "kebun.",
 "p6_not": "EMPAT HAL YANG TIDAK DIBUKTIKAN DI SINI",
 "p6_n1_h": "Niat.",
 "p6_n1_b": "Data observasional tidak memisahkan membakar untuk menanam "
            "dari membuka lahan dengan api di tanah yang memang akan "
            "ditanami, dan keduanya dari sama-sama mengikuti tanah yang "
            "datar, kering dan mudah dijangkau. Jeda satu tahun itu "
            "relevan, tetapi tidak menuntaskannya.",
 "p6_n2_h": "Pelanggaran hukum.",
 "p6_n2_b": "Batas kawasan hutan berubah, dan pelepasan serta tukar "
            "menukar terjadi. Sel yang kini di dalam HPT bisa saja "
            "berstatus APL ketika sawitnya ditanam. Hanya SK untuk bidang "
            "itu yang memastikannya.",
 "p6_n3_h": "Pembukaan lahan kecil — dan ini yang paling penting.",
 "p6_n3_b": "MCD64A1 beresolusi 500 m dan tidak bisa melihat kebakaran "
            "beberapa hektare. Itulah skala kasus Dharmasraya dan "
            "mungkin sebagian besar jalurnya. Angka HPT yang nyaris nol "
            "di halaman 2 adalah pernyataan tentang kemampuan sensor, "
            "bukan tentang apa yang terjadi.",
 "p6_n4_h": "Kebakaran yang mana.",
 "p6_n4_b": "Sel yang terbakar lebih dari sekali dihitung pada kebakaran "
            "pertamanya, sehingga kebakaran ulang sebelum penanaman tidak "
            "terlihat di sini.",
},
}
