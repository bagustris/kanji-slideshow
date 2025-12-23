# Kanji Slideshow  
Automatic learning kanji through wallpaper slideshow. An example is below.  

![Example](./JLPT-N2-SAMPLE/JLPT_N2-SAMPLE_00007.png)

# Required packages
This package requires the following Python packages:
- Pillow
- playwright

# Generate images  

```bash
python3 generate_kanji_images.py kanji_n2.csv # for N2
```

To generate images that match your screen resolution:

```bash
python3 generate_kanji_images.py --screen kanji_n2.csv
```

Or specify a custom size:

```bash
python3 generate_kanji_images.py --width 2560 --height 1440 kanji_n2.csv
```
If run without CSV file, it will generate images for all JLPT levels (N5 to N2):

```bash
python3 generate_kanji_images.py
```
# Use as slideshow
Use shotwell to set wallpaper slideshow. Information is given [here](https://bagustris.blogspot.com/2020/ ,.,12/belajar-kanji-otomatis-lewat-wallpaper.html) (In Indonesian language, right click translate to English).

To scale the image properly, use the following command:  

```bash
gsettings set org.gnome.desktop.background picture-options "scaled"
```
