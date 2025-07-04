import os
import re
import textwrap
import asyncio
import pdfplumber
import edge_tts
from pathlib import Path
from pydub import AudioSegment
import argparse

# --- NORMALIZZAZIONE DEL TESTO ---
def normalize_text(text):
    # Rimuove spazi multipli all'interno delle righe, ma conserva paragrafi
    paragraphs = text.split('\n\n')
    cleaned_paragraphs = []

    for p in paragraphs:
        # pulizia interna ma senza unire tutto
        p_clean = re.sub(r'\s{2,}', ' ', p)
        p_clean = re.sub(r'\n', ' ', p_clean)  # unisce le righe interne di ogni paragrafo
        cleaned_paragraphs.append(p_clean.strip())

    return '\n\n'.join(cleaned_paragraphs)  # ripristina divisione tra paragrafi

# --- FORMATTAZIONE TITOLI E SEZIONI CON SSML ---
def format_titles(text):
    # Titoli in MAIUSCOLO
    text = re.sub(r'(?m)^(?P<title>[A-Z\s]{5,})$', r'<break time="700ms"/><emphasis level="strong">\g<title></emphasis><break time="500ms"/>', text)

    # Sezioni numerate tipo "1. Titolo"
    text = re.sub(r'(?m)^(?P<num>\d+\.\s+.*?)$', r'<break time="700ms"/><emphasis level="moderate">\g<num></emphasis><break time="400ms"/>', text)

    return text

# --- DIVISIONE DEL TESTO IN BLOCCHI ---
def split_text(text, max_len):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) < max_len:
            current += sentence + " "
        else:
            chunks.append(current.strip())
            current = sentence + " "
    if current:
        chunks.append(current.strip())

    return chunks

# --- ESTRAZIONE DEL TESTO DAL PDF ---
def read_file(pdf_files):
    completed_text = ''
    for file in pdf_files:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                lines = text.split('\n')

                # Rimuove numeri di pagina
                cleaned_lines = [
                    line for line in lines
                    if not re.match(r'^(page\s*)?\d+(\s*/\s*\d+)?$', line.strip(), re.IGNORECASE)
                ]

                # Rimuove note tipo [1]
                cleaned_text = '\n'.join(cleaned_lines)
                cleaned_text = re.sub(r'\[\d+\]', '', cleaned_text)

                completed_text += cleaned_text + '\n\n'

    return completed_text

# --- TEXT TO SPEECH ---
async def text_to_speech_edge_tts(chunks, output_path, file_name):
    from time import sleep

    voice = "it-IT-IsabellaNeural"
    output_path.mkdir(exist_ok=True)
    parts = []
    total = len(chunks)

    print("\n🚀 Inizio sintesi vocale...\n")

    for index, chunk in enumerate(chunks, start=1):
        part_file = output_path / f"part_{index}.mp3"
        communicate = edge_tts.Communicate(text=chunk, voice=voice)
        await communicate.save(str(part_file))
        parts.append(part_file)

        # --- Progress bar ---
        perc = round(100 * index / total)
        bar_length = 50
        filled = round(bar_length * perc / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f"[{bar}] {index:>3}/{total}  {perc:>3d}%", end='\r')

    print("\n\n🔊 Unione dei blocchi audio in corso...")

    # Unione dei file mp3
    combined = AudioSegment.empty()
    for part in parts:
        combined += AudioSegment.from_mp3(part)

    final_audio = output_path / f"{file_name}.mp3"
    combined.export(final_audio, format="mp3")
    print(f"\n✅ Audio finale salvato in: {final_audio.resolve()}")
    delete_part_audio(parts, output_path, file_name)

# --- ELIMINAZIONE DEI BLOCCHI AUDIO ---
def delete_part_audio(parts, output_path, file_name):
    total = len(parts)
    print('\n')
    print("🗑️ Eliminazione partizioni audio...")

    for index, part in enumerate(parts, start=1):
        if part.exists():
            part.unlink()

        perc = round(100 * index / total)
        print(f"⏳ Eliminazione... {perc}% ({index}/{total})", end='\r', flush=True)

    print("\n✅ Eliminazione completata.")

# --- FUNZIONE PRINCIPALE ---
def main():
    inp_dir = Path(__file__).parent / 'input'
    output_dir = Path(__file__).parent / 'output'
    parser = argparse.ArgumentParser(description="Text or PDF")
    parser.add_argument('-t', '--text', action='store_true', help='Lettura da file di testo')

    args = parser.parse_args()

    if args.text:
        print("📝 Modalità testo.\n")
        txt_file = list(inp_dir.glob('*.txt'))

        if not txt_file:
            print("❌ Nessun txt trovato nella cartella /input")
            return
        
        text = ""
        for txt in txt_file:
            with open(txt, 'r', encoding='utf-8') as f:
                text = f.read()
            
            chunks = split_text(text, max_len=3000)
            print(f"📝 Numero di caratteri: {len(text)}")
            print(f"📚 Numero di blocchi: {len(chunks)}")

            asyncio.run(text_to_speech_edge_tts(chunks, output_dir,file_name=txt.stem))
    else:
        print("📄 Modalità PDF.")
        pdf_files = list(inp_dir.glob('*.pdf'))

        if not pdf_files:
            print("❌ Nessun PDF trovato nella cartella /input")
            return
        
        print("📄 Estrazione e pulizia del testo...")
        text = read_file(pdf_files)
        text = normalize_text(text)
        text = format_titles(text)

        chunks = split_text(text, max_len=3000)

        print(f"📝 Numero di caratteri: {len(text)}")
        print(f"📚 Numero di blocchi: {len(chunks)}")

        asyncio.run(text_to_speech_edge_tts(chunks, output_dir))

    print("\n🎉 Sintesi vocale completata con successo!")


# --- AVVIO ---
if __name__ == "__main__":
    main()
