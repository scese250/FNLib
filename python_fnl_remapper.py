import os
import struct
import zlib
from PIL import Image, ImageDraw, ImageFont

FONTHACK_MAP = {
    '¿': 'ﾐ', 'Ñ': 'ｰ', 'ñ': 'ｯ', 'ô': 'ﾔ', 'ò': 'ﾒ', 'Õ': 'ｵ', 'Û': 'ｻ', 'Ô': 'ｴ', 'Î': 'ｮ', 'Ê': 'ｪ', 'Ì': 'ｬ', 'Í': 'ｭ', 'Á': '｡', 'É': 'ｩ', 'È': 'ｨ', 'Â': 'ｫ', 'Ç': 'ｧ', 'Ò': 'ｲ', 'Ó': 'ｳ', 'ì': 'ﾌ', 'è': 'ﾈ', 'Ù': 'ｹ', 'Ú': 'ｺ', 'ù': 'ﾙ', 'â': 'ﾂ', 'à': 'ﾀ', 'ê': 'ﾊ', 'ç': 'ﾇ', 'õ': 'ﾕ', 'ã': 'ﾃ', 'í': 'ﾍ', 'á': 'ﾁ', 'é': 'ﾉ', 'ó': 'ﾓ', 'ú': 'ﾚ', 'À': 'ｦ', 'Ë': 'ｱ', 'ë': 'ｶ', 'î': 'ｸ', 'Ï': 'ｼ', 'û': 'ｾ', 'ü': 'ｿ', 'Ü': 'ﾄ', 'œ': 'ﾆ', 'æ': 'ﾋ'
}

def sjis_to_index(code):
    if code < 0x20: return 0
    if code < 0x7f: return code - 0x20
    if code < 0xa1: return 0
    if code < 0xe0: return code - 0x42
    fst = code >> 8
    snd = code & 0xFF
    if fst < 0x81: return 0
    if snd < 0x40 or snd == 0x7f or snd > 0xfc: return 0
    return code - (0x80A2 + (68 * (fst - 0x81)) + (1 if snd > 0x7F else 0))

def get_char_index(char):
    b = char.encode('shift_jis')
    code = b[0] if len(b) == 1 else (b[0] << 8) | b[1]
    return sjis_to_index(code)

TARGET_INDICES = {get_char_index(v): k for k, v in FONTHACK_MAP.items()}

def create_1bpp_glyph(char, height):
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size=height)
    except:
        font = ImageFont.load_default()
        
    bbox = font.getbbox(char)
    if bbox is None:
        width = height // 2
    else:
        width = bbox[2]
        
    if width <= 0: width = 1
        
    img = Image.new('1', (width, height), color=0)
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), char, font=font, fill=1)
    
    new_width = width
    if new_width % 8 != 0:
        new_width += 8 - (new_width % 8)
    if (new_width // 8) % 4 != 0:
        new_width += (4 - ((new_width // 8) % 4)) * 8
        
    padded_img = Image.new('1', (new_width, height), color=0)
    padded_img.paste(img, (0, 0))
    
    padded_img = padded_img.transpose(Image.FLIP_TOP_BOTTOM)
    
    raw_data = padded_img.tobytes()
    return width, zlib.compress(raw_data, level=zlib.Z_BEST_COMPRESSION)

def process_fnl(in_file, out_file):
    print("Reading FNL from", in_file)
    with open(in_file, 'rb') as f:
        data = f.read()
        
    offset = 0
    sig, ver, fnasize, tex_off = struct.unpack_from('<IIII', data, offset)
    offset += 16
    
    num_fonts = struct.unpack_from('<I', data, offset)[0]
    offset += 4
    
    fonts = []
    for f_idx in range(num_fonts):
        num_tables = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        tables = []
        for t_idx in range(num_tables):
            h, pad, num_glyphs = struct.unpack_from('<iii', data, offset)
            offset += 12
            
            glyphs = []
            for g_idx in range(num_glyphs):
                g_w, g_to, g_ts = struct.unpack_from('<HII', data, offset)
                offset += 10
                glyphs.append({'w': g_w, 'to': g_to, 'ts': g_ts, 'idx': g_idx})
            
            tables.append({'h': h, 'pad': pad, 'glyphs': glyphs})
        fonts.append(tables)
        
    print(f"Header parsed. Texture data starts at {tex_off}.")
    
    print("Redrawing glyphs and building new textures...")
    new_texture_data = bytearray()
    
    for f_idx, tables in enumerate(fonts):
        for t_idx, table in enumerate(tables):
            h = table['h']
            for glyph in table['glyphs']:
                g_idx = glyph['idx']
                if g_idx in TARGET_INDICES:
                    vchar = TARGET_INDICES[g_idx]
                    new_w, comp_data = create_1bpp_glyph(vchar, h)
                    glyph['w'] = new_w
                    if len(comp_data) > 0:
                        glyph['to'] = len(new_texture_data) 
                        glyph['ts'] = len(comp_data)
                        new_texture_data.extend(comp_data)
                    else:
                        glyph['to'] = 0
                        glyph['ts'] = 0
                else:
                    if glyph['to'] != 0 and glyph['ts'] != 0:
                        old_tex = data[tex_off + glyph['to'] : tex_off + glyph['to'] + glyph['ts']]
                        glyph['to'] = len(new_texture_data)
                        new_texture_data.extend(old_tex)
                    else:
                        glyph['to'] = 0
                        glyph['ts'] = 0
                        
    print("Writing new FNL to", out_file)
    with open(out_file, 'wb') as f:
        f.write(struct.pack('<IIII', 0x414e46, 0, 0, 0))
        f.write(struct.pack('<I', len(fonts)))
        for tables in fonts:
            f.write(struct.pack('<I', len(tables)))
            for table in tables:
                f.write(struct.pack('<iii', table['h'], table['pad'], len(table['glyphs'])))
                for glyph in table['glyphs']:
                    f.write(struct.pack('<HII', glyph['w'], glyph['to'], glyph['ts']))
                    
        actual_tex_off = f.tell()
        f.write(new_texture_data)
        actual_size = f.tell() - actual_tex_off
        f.seek(0)
        f.write(struct.pack('<IIII', 0x414e46, 0, actual_size, actual_tex_off))
        
    print("Done! Repacked to", out_file)

if __name__ == '__main__':
    process_fnl('dohnadohnaFont_original.fnl', 'dohnadohnaFont.fnl')
