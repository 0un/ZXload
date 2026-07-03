#!/data/data/com.termux/files/usr/bin/python
import sys
import os
import struct
import wave
import subprocess

# Тайминги ZX Spectrum для генерации звука
SAMPLE_RATE = 44100
T_STATES_PER_SEC = 3500000

PILOT_PULSE = 2168
SYNC1_PULSE = 667
SYNC2_PULSE = 735
BIT0_PULSE = 855
BIT1_PULSE = 1710

def generate_pulse(duration_t_states, level, wav_file):
    """Генерирует импульс и записывает его в WAV-файл."""
    duration_sec = duration_t_states / T_STATES_PER_SEC
    num_samples = int(round(duration_sec * SAMPLE_RATE))
    val = 30 if level else 220
    frame_data = bytes([val]) * num_samples
    wav_file.writeframes(frame_data)

def parse_tzx_to_blocks(file_path):
    """Извлекает блоки данных из стандартного TZX файла."""
    blocks = []
    with open(file_path, "rb") as f:
        header = f.read(10)
        if header[:7] != b"ZXTape!":
            print("[!] Ошибка: Неверный заголовок TZX файла.")
            return None
        
        while True:
            id_byte = f.read(1)
            if not id_byte:
                break
            block_id = id_byte[0]

            if block_id == 0x10:  # Standard Speed Data Block
                f.read(2)  # Pause after this block
                data_length = struct.unpack("<H", f.read(2))[0]
                block_data = f.read(data_length)
                blocks.append(block_data)
            elif block_id == 0x11:  # Turbo Speed Data Block
                f.read(15)  # Пропуск таймингов пилотов и бит
                len_bytes = f.read(3)
                if len(len_bytes) < 3:
                    break
                data_length = struct.unpack("<I", len_bytes + b"\x00")[0]
                block_data = f.read(data_length)
                blocks.append(block_data)
            elif block_id in [0x30, 0x31, 0x32]:  # Текстовые описания / сообщения
                length_byte = f.read(1)
                if not length_byte: break
                f.read(length_byte[0])
            elif block_id == 0x20:  # Pause block
                f.read(2)
            elif block_id == 0x21:  # Group start
                length_byte = f.read(1)
                if not length_byte: break
                f.read(length_byte[0])
            elif block_id in [0x22, 0x23, 0x24, 0x25]:  # Управление группами/циклами
                pass 
            else:
                # Если блок неизвестен, TZX не гарантирует фиксированный размер.
                # Большинство кастомных утилит затыкаются здесь. 
                # Для стабильности выходим, если базовые блоки уже прочитаны.
                pass
    return blocks

def parse_tap_to_blocks(file_path):
    """Извлекает блоки данных из стандартного TAP файла."""
    blocks = []
    with open(file_path, "rb") as f:
        while True:
            length_bytes = f.read(2)
            if not length_bytes:
                break
            block_length = struct.unpack("<H", length_bytes)[0]
            block_data = f.read(block_length)
            blocks.append(block_data)
    return blocks

def play_audio_file(wav_path, apply_inversion=False):
    """Воспроизводит готовый WAV файл через Sox"""
    print("[*] Запуск воспроизведения...")
    try:
        cmd = ["play", wav_path]
        if apply_inversion:
            cmd.extend(["vol", "-1.0"])
            
        subprocess.run(cmd)
    except FileNotFoundError:
        print("[!] Ошибка: Не найдена утилита play. Выполните в Termux: pkg install sox")
    except KeyboardInterrupt:
        print("\n[-] Воспроизведение прервано пользователем.")

def generate_wav_and_play(blocks):
    """Генерирует временный WAV файл и отправляет его на воспроизведение."""
    temp_wav = "temp_output.wav"
    print(f"[*] Генерация звуковой дорожки из {len(blocks)} блоков...")

    with wave.open(temp_wav, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(SAMPLE_RATE)

        level = False

        # 1 секунда тишины в начале
        w.writeframes(bytes([128]) * int(SAMPLE_RATE * 1.0))

        for block_data in blocks:
            if not block_data or len(block_data) < 1:
                continue
            flag_byte = block_data[0]
            is_header = (flag_byte < 128)

            # 1. Пилот-тон
            pilot_count = 8063 if is_header else 3223
            for _ in range(pilot_count):
                generate_pulse(PILOT_PULSE, level, w)
                level = not level

            # 2. Синхросигналы
            generate_pulse(SYNC1_PULSE, level, w)
            level = not level
            generate_pulse(SYNC2_PULSE, level, w)
            level = not level

            # 3. Данные
            for byte in block_data:
                for i in range(7, -1, -1):
                    bit = (byte >> i) & 1
                    pulse_len = BIT1_PULSE if bit else BIT0_PULSE
                    
                    generate_pulse(pulse_len, level, w)
                    level = not level
                    generate_pulse(pulse_len, level, w)
                    level = not level

            # 4. Пауза после каждого блока (1 секунда тишины)
            w.writeframes(bytes([128]) * SAMPLE_RATE)

    play_audio_file(temp_wav, apply_inversion=True)
    
    if os.path.exists(temp_wav):
        os.remove(temp_wav)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: ./load.py <имя_файла.tap/.tzx/.wav>")
        sys.exit(1)
    
    target_file = sys.argv[1]
    
    if not os.path.exists(target_file):
        print(f"[!] Ошибка: Файл '{target_file}' не найден.")
        sys.exit(1)
        
    _, file_extension = os.path.splitext(target_file)
    file_extension = file_extension.lower()
    
    if file_extension == '.wav':
        print(f"[*] Обнаружен готовый аудиофайл WAV.")
        play_audio_file(target_file, apply_inversion=False)
        print("\n[+] Воспроизведение файла завершено.")
    else:
        if file_extension == '.tzx':
            data_blocks = parse_tzx_to_blocks(target_file)
        else:
            data_blocks = parse_tap_to_blocks(target_file)
            
        if data_blocks:
            generate_wav_and_play(data_blocks)
            print("\n[+] Загрузка успешно завершена.")
        else:
            print("[!] Ошибка: Не удалось извлечь данные из файла.")
