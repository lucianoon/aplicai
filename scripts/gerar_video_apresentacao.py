"""Gerador do vídeo de apresentação oficial do Aplicaí.
Combina os prints das telas com narração sintetizada (gTTS pt-br),
legendas automáticas e slides em resolução Full HD (1920x1080).
Gera o arquivo final: docs/apresentacao/apresentacao_aplicai.mp4
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

RAIZ = Path(__file__).resolve().parents[1]
PRINTS_DIR = RAIZ / "docs" / "apresentacao" / "prints-demo"
OUTPUT_DIR = RAIZ / "docs" / "apresentacao"
OUTPUT_VIDEO = OUTPUT_DIR / "apresentacao_aplicai.mp4"

FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Cores oficiais da identidade
COR_AZUL_ITAU = (0, 51, 153)       # #003399
COR_LARANJA = (236, 112, 0)        # #EC7000
COR_FUNDO = (245, 247, 250)         # Cinza suave
COR_CARD = (255, 255, 255)          # Branco
COR_TEXTO_ESCURO = (20, 30, 45)
COR_TEXTO_MUTED = (100, 116, 139)
COR_BORDA = (226, 232, 240)
COR_BANNER_LEGENDA = (15, 23, 42, 230)

CENAS = [
    {
        "id": "01_abertura",
        "tipo": "slide",
        "titulo": "Aplicaí",
        "subtitulo": "Gestor de Liquidez & Investimentos com IA",
        "destaque": "A sobra do mês rendendo, sem nunca faltar para as contas.",
        "topicos": [
            "Análise de 467 mil transações de 1.000 clientes da base real",
            "50% dos clientes têm sobra que fica parada a 0% por medo de faltar",
            "O robô comum deixa o risco com o cliente; o Aplicaí protege as contas",
        ],
        "audio_texto": (
            "Analisamos as 467 mil transações de mil clientes da base do evento. "
            "Metade deles ganha mais do que gasta, e essa sobra fica parada na conta rendendo zero. "
            "Por que não aplicam? Porque têm medo de faltar: o financiamento vence no dia 8, a escola no dia 10, a fatura no fim do mês. "
            "E o robô de investimento comum não olha nada disso: oferece o produto e deixa o risco com o cliente."
        ),
        "legenda": "Problema: Metade dos clientes tem sobra parada a 0% por medo de faltar para as contas.",
    },
    {
        "id": "02_promessa",
        "tipo": "slide",
        "titulo": "A Promessa do Aplicaí",
        "subtitulo": "Inteligência com Segurança Determinística",
        "destaque": "A IA conversa, o código calcula e o cliente decide.",
        "topicos": [
            "Projeta os próximos 30 dias de entradas e saídas",
            "Reserva o colchão de contas futuras antes de qualquer oferta",
            "Aplica apenas a sobra real em CDB Liquidez Diária (100% CDI com FGC)",
            "A IA não movimenta dinheiro nem faz contas: total transparência",
        ],
        "audio_texto": (
            "O Aplicaí faz a sobra do mês render sem nunca tocar no dinheiro das contas. "
            "Ele projeta os próximos 30 dias, reserva o que vai sair e sugere aplicar só o que passa disso, "
            "num CDB de liquidez diária com garantia do FGC, o investimento mais conservador que existe. "
            "De propósito: é dinheiro que o cliente pode precisar no mês que vem, então liquidez diária é requisito, não limitação. "
            "E tem uma regra que nenhum robô tem: a IA conversa, mas não faz conta nem movimenta dinheiro. "
            "O código calcula, e o cliente aprova."
        ),
        "legenda": "A promessa: Projeção de 30 dias, reserva das contas e aplicação apenas da sobra em CDB com FGC.",
    },
    {
        "id": "03_diego_card",
        "tipo": "print",
        "print_file": "diego_01_card_aplicar.png",
        "titulo_tela": "Diego Takahashi - Identificação da Sobra Ociosa",
        "audio_texto": (
            "O Diego tem 38 mil e 250 reais na conta. "
            "Sem digitar nada, ele já vê: 9 mil e 700 reservados para a fatura, o financiamento e o dia a dia, "
            "e 28 mil e 550 parados. O perfil de investidor dele está em dia, e o produto sugerido é o conservador."
        ),
        "legenda": "Diego (C004): R$ 9.700 reservados para contas e R$ 28.550 identificados como sobra livre.",
    },
    {
        "id": "04_diego_aprovacao",
        "tipo": "print",
        "print_file": "diego_02_aprovacao.png",
        "titulo_tela": "Cotação Determinística e Aprovação com iToken",
        "audio_texto": (
            "Ao tocar em aplicar, ele vê o valor exato, o rendimento líquido previsto e a garantia do FGC, e aprova. "
            "Só com essa aprovação o sistema emite uma autorização com assinatura digital, e o banco refaz a conta antes de executar."
        ),
        "legenda": "Cotação transparente com rendimento líquido e impostos; aprovação segura via iToken.",
    },
    {
        "id": "05_diego_comprovante",
        "tipo": "print",
        "print_file": "diego_03_comprovante.png",
        "titulo_tela": "Execução Autorizada com Trilha de Auditoria",
        "audio_texto": (
            "Pronto: 28 mil e 550 reais rendendo, e as contas do mês totalmente protegidas. "
            "Se o Diego tentasse aplicar o saldo inteiro de 38 mil, o sistema recusaria, porque faltaria dinheiro para o financiamento."
        ),
        "legenda": "Operação assinada com recibo digital único. Saldo aplicado sem comprometer despesas.",
    },
    {
        "id": "06_diego_saldo",
        "tipo": "print",
        "print_file": "diego_04_saldo_atualizado.png",
        "titulo_tela": "Visão Atualizada da Conta e Custódia",
        "audio_texto": (
            "A conta corrente agora reflete o colchão de segurança reservado, e a custódia de investimentos passa a render imediatamente a 100% do CDI."
        ),
        "legenda": "Saldo disponível alinhado às contas do mês e reserva investida em liquidez diária.",
    },
    {
        "id": "07_carla",
        "tipo": "print",
        "print_file": "carla_01_acolhimento.png",
        "titulo_tela": "Carla Pereira - Superendividamento e Acolhimento",
        "audio_texto": (
            "A Carla está com a conta negativa. O Aplicaí não oferece investimento nenhum: os juros da dívida dela são maiores que qualquer rendimento. "
            "Ele acolhe e encaminha para renegociação com uma pessoa especializada, em estrito respeito à Lei do Superendividamento."
        ),
        "legenda": "Carla (C003): Proteção Lei 14.181 - Bloqueio de investimentos e encaminhamento humanizado.",
    },
    {
        "id": "08_elaine",
        "tipo": "print",
        "print_file": "elaine_01_perfil_pendente.png",
        "titulo_tela": "Elaine Costa - Sobra sem Perfil de Investidor",
        "audio_texto": (
            "A Elaine tem 17 mil e 150 reais sobrando, mas nunca respondeu o perfil de investidor. "
            "Sem perfil válido, não há oferta: o aplicativo solicita a atualização primeiro. "
            "Essas travas não dependem do modelo de linguagem: mesmo que alguém tentasse forçar a aplicação, o core bancário recusaria."
        ),
        "legenda": "Elaine (C005): Trava de Suitability (CVM) - Sem perfil de investidor válido, não há oferta.",
    },
    {
        "id": "09_protecoes",
        "tipo": "print",
        "print_file": "protecoes_01_dado_de_terceiro.png",
        "titulo_tela": "Arquitetura Segura, LGPD e Guardrails",
        "audio_texto": (
            "Nossa segurança opera em três níveis. "
            "Primeiro: a inteligência artificial não faz contas matemáticas; cálculos são código validado por 156 testes automáticos. "
            "Segundo: nenhuma ação movimenta dinheiro sem aprovação e autorização criptográfica de 60 segundos. "
            "Terceiro: privacidade integral, mascaramento de dados sensíveis e bloqueio contra manipulações ou acesso a dados de terceiros."
        ),
        "legenda": "Segurança em camadas: Mascaramento LGPD, Guardrails anti-injeção e 156 testes automáticos.",
    },
    {
        "id": "10_ana_fatura",
        "tipo": "print",
        "print_file": "ana_01_card_fatura.png",
        "titulo_tela": "Ana Souza - O Outro Lado da Mesma Regra",
        "audio_texto": (
            "E quando o mês não fecha? O mesmo motor preditivo que protege o Diego atua para proteger a Ana de juros abusivos."
        ),
        "legenda": "Ana (C001): Déficit imprevisto no mês - Alerta proativo antes do vencimento da fatura.",
    },
    {
        "id": "11_ana_chat",
        "tipo": "print",
        "print_file": "ana_02_opcoes_no_chat.png",
        "titulo_tela": "Orientação Financeira Transparente no Chat",
        "audio_texto": (
            "Ao conversar no chat, o Aplicaí calcula a alternativa mais barata: pagar 549 reais à vista e parcelar o restante em 6 vezes, "
            "economizando 375 reais em relação ao rotativo do cartão. Para quem está no aperto, o melhor investimento é evitar juros."
        ),
        "legenda": "Economia de R$ 375,10 evitando rotativo abusivo com parcelamento inteligente.",
    },
    {
        "id": "12_conclusao",
        "tipo": "slide",
        "titulo": "Aplicaí - Itaú Unibanco",
        "subtitulo": "Solução de Alto Impacto para Milhões de Brasileiros",
        "destaque": "A sobra do mês rendendo, sem nunca faltar para as contas.",
        "topicos": [
            "Arquitetura 100% Google Cloud (Cloud Run, Vertex AI Gemini 3.5, Secret Manager, BigQuery)",
            "156 testes automáticos garantindo integridade e conformidade",
            "Impacto real: previne endividamento e gera rentabilidade acessível",
            "A IA conversa, o código calcula e o cliente decide.",
        ],
        "audio_texto": (
            "Aplicaí: a sobra do mês rendendo, sem nunca faltar para as contas. "
            "A inteligência artificial conversa, o código calcula e o cliente decide. Muito obrigado!"
        ),
        "legenda": "Aplicaí: inteligência financeira preventiva com segurança, governança e foco no cliente.",
    },
]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def render_slide(cena: dict) -> Image.Image:
    img = Image.new("RGB", (1920, 1080), COR_FUNDO)
    draw = ImageDraw.Draw(img)

    font_title = ImageFont.truetype(FONT_BOLD_PATH, 56)
    font_sub = ImageFont.truetype(FONT_REGULAR_PATH, 30)
    font_destaque = ImageFont.truetype(FONT_BOLD_PATH, 36)
    font_item = ImageFont.truetype(FONT_REGULAR_PATH, 28)
    font_badge = ImageFont.truetype(FONT_BOLD_PATH, 22)

    # Top header bar
    draw.rectangle([(0, 0), (1920, 140)], fill=COR_AZUL_ITAU)
    draw.rectangle([(0, 134), (1920, 140)], fill=COR_LARANJA)

    # Badge Itaú
    draw.rounded_rectangle([(100, 35), (280, 105)], radius=12, fill=COR_LARANJA)
    draw.text((120, 48), "Itaú Hack", font=font_badge, fill=(255, 255, 255))

    # Header title
    draw.text((320, 42), cena["titulo"], font=font_title, fill=(255, 255, 255))

    # Subtitle under top bar
    draw.text((100, 175), cena["subtitulo"], font=font_sub, fill=COR_TEXTO_MUTED)

    # Main content card
    draw.rounded_rectangle([(100, 240), (1820, 920)], radius=20, fill=COR_CARD, outline=COR_BORDA, width=2)

    # Highlight box inside card
    draw.rounded_rectangle([(140, 280), (1780, 380)], radius=12, fill=(254, 243, 199))  # soft amber
    draw.rectangle([(140, 280), (155, 380)], fill=COR_LARANJA)
    draw.text((180, 310), f"★  {cena['destaque']}", font=font_destaque, fill=(180, 83, 9))

    # Bullets
    y = 440
    bullet_font = ImageFont.truetype(FONT_BOLD_PATH, 30)
    for topico in cena["topicos"]:
        draw.text((160, y), "✔", font=bullet_font, fill=COR_LARANJA)
        lines = wrap_text(draw, topico, font_item, 1500)
        for line in lines:
            draw.text((220, y + 2), line, font=font_item, fill=COR_TEXTO_ESCURO)
            y += 45
        y += 25

    # Bottom subtitle banner
    render_legenda(draw, cena["legenda"])
    return img


def render_print(cena: dict) -> Image.Image:
    img = Image.new("RGB", (1920, 1080), COR_FUNDO)
    draw = ImageDraw.Draw(img)

    font_header = ImageFont.truetype(FONT_BOLD_PATH, 42)
    font_badge = ImageFont.truetype(FONT_BOLD_PATH, 20)

    # Header bar
    draw.rectangle([(0, 0), (1920, 110)], fill=COR_AZUL_ITAU)
    draw.rectangle([(0, 106), (1920, 110)], fill=COR_LARANJA)

    draw.rounded_rectangle([(70, 25), (220, 85)], radius=10, fill=COR_LARANJA)
    draw.text((88, 38), "Aplicaí", font=font_badge, fill=(255, 255, 255))

    draw.text((250, 32), cena["titulo_tela"], font=font_header, fill=(255, 255, 255))

    # Load and place the screenshot
    print_path = PRINTS_DIR / cena["print_file"]
    if print_path.exists():
        screenshot = Image.open(print_path)
        # Screenshot is 1100x900. Scale to fit nicely with border: e.g. 1000x818
        orig_w, orig_h = screenshot.size
        target_h = 800
        target_w = int(orig_w * (target_h / orig_h))
        scaled_shot = screenshot.resize((target_w, target_h), Image.Resampling.LANCZOS)

        pos_x = (1920 - target_w) // 2
        pos_y = 135

        # Card shadow / border
        draw.rounded_rectangle([(pos_x - 8, pos_y - 8), (pos_x + target_w + 8, pos_y + target_h + 8)],
                               radius=16, fill=COR_CARD, outline=COR_BORDA, width=3)
        img.paste(scaled_shot, (pos_x, pos_y))

    # Bottom subtitle banner
    render_legenda(draw, cena["legenda"])
    return img


def render_legenda(draw: ImageDraw.ImageDraw, texto: str):
    font_leg = ImageFont.truetype(FONT_BOLD_PATH, 25)
    # Background strip at the bottom
    draw.rectangle([(0, 970), (1920, 1080)], fill=(15, 23, 42))
    draw.rectangle([(0, 970), (1920, 975)], fill=COR_LARANJA)
    # Centered subtitle
    bbox = draw.textbbox((0, 0), texto, font=font_leg)
    text_w = bbox[2] - bbox[0]
    pos_x = max(60, (1920 - text_w) // 2)
    draw.text((pos_x, 1005), texto, font=font_leg, fill=(255, 255, 255))


def get_audio_duration(audio_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="video_aplicai_"))
    print(f"Diretório temporário: {work_dir}")

    clip_paths = []

    try:
        for idx, cena in enumerate(CENAS, 1):
            cena_id = cena["id"]
            print(f"[{idx}/{len(CENAS)}] Processando cena: {cena_id}...")

            # 1. Gerar áudio via gTTS
            audio_file = work_dir / f"{cena_id}.mp3"
            tts = gTTS(cena["audio_texto"], lang="pt-br", tld="com.br")
            tts.save(str(audio_file))

            duracao = get_audio_duration(audio_file)
            # Adiciona 0.8s de margem para respiração visual
            duracao_clip = duracao + 0.8

            # 2. Gerar frame visual
            if cena["tipo"] == "slide":
                frame_img = render_slide(cena)
            else:
                frame_img = render_print(cena)

            frame_file = work_dir / f"{cena_id}.png"
            frame_img.save(str(frame_file))

            # 3. Gerar clipe com ffmpeg
            clip_file = work_dir / f"{cena_id}.mp4"
            cmd_clip = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(frame_file),
                "-i", str(audio_file),
                "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
                "-t", f"{duracao_clip:.2f}",
                "-shortest",
                str(clip_file)
            ]
            subprocess.run(cmd_clip, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            clip_paths.append(clip_file)
            print(f"   -> Clipe gerado ({duracao_clip:.1f}s)")

        # 4. Concatenar todos os clipes no vídeo final
        print("Concatenando todos os clipes...")
        concat_txt = work_dir / "concat.txt"
        with open(concat_txt, "w") as f:
            for p in clip_paths:
                f.write(f"file '{p.resolve()}'\n")

        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-c", "copy",
            str(OUTPUT_VIDEO)
        ]
        subprocess.run(cmd_concat, check=True)
        print(f"Vídeo de apresentação gerado com sucesso em: {OUTPUT_VIDEO}")

        # Obter duração total do vídeo
        duracao_total = get_audio_duration(OUTPUT_VIDEO)
        minutos = int(duracao_total // 60)
        segundos = int(duracao_total % 60)
        tamanho_mb = OUTPUT_VIDEO.stat().st_size / (1024 * 1024)
        print(f"Duração total: {minutos}m {segundos}s | Tamanho: {tamanho_mb:.2f} MB")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
