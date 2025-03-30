from flask import Flask, request, jsonify, send_file
import os
import base64
import subprocess
from pypdf import PdfWriter, PdfReader
from pypdf.generic import RectangleObject
import sys
import copy

class PDFTranslator:
    DEFAULT_CONFIG = {
        'port': 8888,
        'engine': 'pdf2zh',
        'service': 'bing',
        'threadNum': 4,
        'outputPath': './translated/',
        'configPath': './config.json',
        'sourceLang': 'en',
        'targetLang': 'zh'
    }

    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
        self.translated_dir = self.DEFAULT_CONFIG['outputPath']

    def setup_routes(self):
        self.app.add_url_rule('/translate', 'translate', self.translate, methods=['POST'])
        self.app.add_url_rule('/cut', 'cut', self.cut_pdf, methods=['POST'])
        self.app.add_url_rule('/cut-compare', 'cut_compare', self.cut_compare, methods=['POST'])
        self.app.add_url_rule('/translatedFile/<filename>', 'download', self.download_file)

    class Config:
        def __init__(self, data):
            self.threads = data.get('threadNum', PDFTranslator.DEFAULT_CONFIG['threadNum'])
            self.service = data.get('service', PDFTranslator.DEFAULT_CONFIG['service'])
            self.engine = data.get('engine', PDFTranslator.DEFAULT_CONFIG['engine'])
            self.outputPath = self.get_abs_path(data.get('outputPath', PDFTranslator.DEFAULT_CONFIG['outputPath']))
            self.configPath = self.get_abs_path(data.get('configPath', PDFTranslator.DEFAULT_CONFIG['configPath']))
            self.sourceLang = data.get('sourceLang', PDFTranslator.DEFAULT_CONFIG['sourceLang'])
            self.target_lang = data.get('targetLang', PDFTranslator.DEFAULT_CONFIG['targetLang'])
            self.babeldoc = data.get('babeldoc', False)
            self.mono_cut = data.get('mono_cut', False)
            self.dual_cut = data.get('dual_cut', False)
            self.compare = data.get('compare', False)
            
            os.makedirs(self.outputPath, exist_ok=True)

        @staticmethod
        def get_abs_path(path):
            return path if os.path.isabs(path) else os.path.abspath(path)

    def process_request(self):
        data = request.get_json()
        config = self.Config(data)
        
        file_content = data.get('fileContent', '')
        if file_content.startswith('data:application/pdf;base64,'):
            file_content = file_content[len('data:application/pdf;base64,'):]
        
        input_path = os.path.join(config.outputPath, data['fileName'])
        with open(input_path, 'wb') as f:
            f.write(base64.b64decode(file_content))
        
        return input_path, config

    def translate_pdf(self, input_path, config):
        base_name = os.path.basename(input_path).replace('.pdf', '')
        output_files = {
            'mono': os.path.join(config.outputPath, f"{base_name}-mono.pdf"),
            'dual': os.path.join(config.outputPath, f"{base_name}-dual.pdf")
        }

        cmd = [
            config.engine,
            input_path,
            '--t', str(config.threads),
            '--output', config.outputPath,
            '--service', config.service,
            '--lang-in', config.sourceLang,
            '--lang-out', config.target_lang,
        ]
        if config.babeldoc:
            cmd.append('--babeldoc')
        if config.configPath:
            cmd.extend(['--config', config.configPath])

        subprocess.run(cmd, check=True)
        return output_files['mono'], output_files['dual']

    def split_pdf(self, input_path, output_path, compare=False):
        writer = PdfWriter()
        if 'dual' in input_path:
            readers = [PdfReader(input_path) for _ in range(4)]
            for i in range(0, len(readers[0].pages), 2):
                original_media_box = readers[0].pages[i].mediabox
                width = original_media_box.width
                height = original_media_box.height

                left_page_1 = readers[0].pages[i]
                for box in ['mediabox', 'cropbox', 'trimbox', 'bleedbox', 'artbox']:
                    setattr(left_page_1, box, RectangleObject((0, 0, width/2, height)))

                left_page_2 = readers[1].pages[i+1]
                for box in ['mediabox', 'cropbox', 'trimbox', 'bleedbox', 'artbox']:
                    setattr(left_page_2, box, RectangleObject((0, 0, width/2, height)))

                right_page_1 = readers[2].pages[i]
                for box in ['mediabox', 'cropbox', 'trimbox', 'bleedbox', 'artbox']:
                    setattr(right_page_1, box, RectangleObject((width/2, 0, width, height)))

                right_page_2 = readers[3].pages[i+1]
                for box in ['mediabox', 'cropbox', 'trimbox', 'bleedbox', 'artbox']:
                    setattr(right_page_2, box, RectangleObject((width/2, 0, width, height)))

                if compare == True:
                    blank_page_1 = writer.add_blank_page(width, height)
                    blank_page_1.merge_transformed_page(left_page_1, (1, 0, 0, 1, 0, 0))
                    blank_page_1.merge_transformed_page(left_page_2, (1, 0, 0, 1, width / 2, 0))
                    blank_page_2 = writer.add_blank_page(width, height)
                    blank_page_2.merge_transformed_page(right_page_1, (1, 0, 0, 1, -width / 2, 0))
                    blank_page_2.merge_transformed_page(right_page_2, (1, 0, 0, 1, 0, 0))
                else:
                    writer.add_page(left_page_1)
                    writer.add_page(left_page_2)
                    writer.add_page(right_page_1)
                    writer.add_page(right_page_2)
        else: 
            readers = [PdfReader(input_path) for _ in range(2)]
            for i in range(len(readers[0].pages)):
                page = readers[0].pages[i]

                original_media_box = page.mediabox
                width = original_media_box.width
                height = original_media_box.height

                left_page = readers[0].pages[i]
                left_page.mediabox = RectangleObject((0, 0, width / 2, height))
                right_page = readers[1].pages[i]
                right_page.mediabox = RectangleObject((width / 2, 0, width, height))

                writer.add_page(left_page)
                writer.add_page(right_page)

        with open(output_path, "wb") as output_file:
            writer.write(output_file)

    def translate(self):
        try:
            input_path, config = self.process_request()
            mono, dual = self.translate_pdf(input_path, config)
            
            processed_files = []
            if config.mono_cut:
                output = mono.replace('-mono.pdf', '-mono-cut.pdf')
                self.split_pdf(mono, output)
                processed_files.append(output)
            
            if config.dual_cut:
                output = dual.replace('-dual.pdf', '-dual-cut.pdf')
                self.split_pdf(dual, output)
                processed_files.append(output)
            
            if config.compare:
                output = dual.replace('-dual.pdf', '-compare.pdf')
                self.split_pdf(dual, output, compare=True)
                processed_files.append(output)
            
            return jsonify({'status': 'success', 'processed': processed_files}), 200
        
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def cut_pdf(self):
        try:
            input_path, config = self.process_request()
            output_path = input_path.replace('.pdf', '-cut.pdf')
            self.split_pdf(input_path, output_path)
            return jsonify({'status': 'success', 'path': output_path}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def cut_compare(self):
        try:
            input_path, config = self.process_request()
            output_path = input_path.replace('.pdf', '-compare.pdf')
            self.split_pdf(input_path, output_path, compare=True)
            return jsonify({'status': 'success', 'path': output_path}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def download_file(self, filename):
        file_path = os.path.join(self.translated_dir, filename)
        return send_file(file_path, as_attachment=True) if os.path.exists(file_path) else ('File not found', 404)

    def run(self):
        port = int(sys.argv[1]) if len(sys.argv) > 1 else self.DEFAULT_CONFIG['port']
        self.app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    translator = PDFTranslator()
    translator.run()