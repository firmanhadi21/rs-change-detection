"""Front and back covers (A4) from a real run in the book.

The image is the Landsat NDVI change 1990–1992 → 2023–2025 in Central
Kalimantan from chapter 10 (buku/hasil/deforestasi-kalteng-landsat). Run from
buku/ after that chapter has rendered:

    python gambar/sampul.py
"""

import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import rasterio

SINI = os.path.dirname(os.path.abspath(__file__))
BUKU = os.path.dirname(SINI)
HIJAU = "#1a5e47"
A4 = (8.27, 11.69)

tif = sorted(glob.glob(os.path.join(BUKU, "hasil", "deforestasi-kalteng-landsat", "*.tif")))[0]
with rasterio.open(tif) as src:
    d = src.read(1).astype(float)
    if src.nodata is not None:
        d[d == src.nodata] = np.nan


def latar(fig):
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, color=HIJAU, transform=ax.transAxes))
    return ax


# ---------------------------------------------------------------- front
fig = plt.figure(figsize=A4)
latar(fig)
img = fig.add_axes([0, 0.36, 1, 0.64])
h, w = d.shape
side = min(h, int(w * 0.64 * A4[1] / A4[0]))
img.imshow(d[:side, :], cmap="RdYlGn", vmin=-0.4, vmax=0.4, interpolation="nearest",
           aspect="auto")
img.set_axis_off()

t = fig.add_axes([0, 0, 1, 0.36])
t.set_axis_off()
t.text(0.08, 0.80, "Deteksi Perubahan\ndengan Citra Satelit", color="white",
       fontsize=34, fontweight="bold", va="top", linespacing=1.15)
t.text(0.08, 0.40, "Panduan praktis earthchange dengan Python\nuntuk kasus-kasus Indonesia",
       color="#d6efe4", fontsize=15, va="top", linespacing=1.4)
t.text(0.08, 0.10, "Firman Hadi · Yasser Wahyuddin · L. M. Sabri", color="white",
       fontsize=12.5, va="bottom")
t.text(0.92, 0.10, "Universitas Diponegoro", color="#d6efe4", fontsize=10,
       va="bottom", ha="right")
fig.text(0.985, 0.37, "Perubahan NDVI Landsat 1990–1992 → 2023–2025, Kalimantan Tengah",
         color="white", fontsize=7, ha="right", va="bottom",
         bbox=dict(facecolor=HIJAU, edgecolor="none", alpha=0.75, pad=3))

for ext, dpi in (("png", 150), ("pdf", None)):
    fig.savefig(os.path.join(SINI, f"sampul-depan.{ext}"), dpi=dpi)
plt.close(fig)

# ---------------------------------------------------------------- back
fig = plt.figure(figsize=A4)
latar(fig)
ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
ax.set_axis_off()
blurb = (
    "Data satelit sudah gratis bertahun-tahun. Kemampuan memakainya belum.\n\n"
    "Buku ini memandu Anda memakai earthchange, paket Python untuk mendeteksi\n"
    "perubahan permukaan bumi dari citra satelit gratis: deforestasi, tambang,\n"
    "banjir, abrasi, kebakaran hutan dan lahan, asap, perpindahan penduduk, dan\n"
    "pulau kecil yang memanas. Setiap analisis cukup satu baris Python.\n\n"
    "Semua angka dan peta di Bagian I dan II keluar dari sel Python yang tercetak\n"
    "di sebelahnya, dijalankan saat buku ini dirender. Bagian terakhir membahas\n"
    "yang sering dilewatkan: batasan data, pilihan lapisan gambut yang bisa\n"
    "mengubah angka empat kali lipat, dan cara melaporkan hasil agar bisa\n"
    "diulang orang lain."
)
ax.text(0, 0.95, blurb, color="white", fontsize=12.5, va="top", linespacing=1.55)
ax.text(0, 0.18, "Teks: CC BY-NC-SA 4.0 · Kode: MIT\n"
        "firmanhadi21.github.io/rs-change-detection/buku\n"
        "pip install earthchange", color="#d6efe4", fontsize=10.5, va="top",
        linespacing=1.6)
fig.savefig(os.path.join(SINI, "sampul-belakang.pdf"))
plt.close(fig)
print("sampul-depan.png, sampul-depan.pdf, sampul-belakang.pdf")
