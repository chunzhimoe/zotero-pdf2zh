#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import yaml
import logging
import requests
import subprocess
import tempfile
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
import copy
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('config_manager')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_secret_key_please_change_this')
app.config['CONFIG_PATH'] = os.environ.get('CONFIG_PATH', '/app/config.json')
app.config['ADMIN_USERNAME'] = os.environ.get('ADMIN_USERNAME', 'admin')
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'admin123')
app.config['ENCRYPTION_KEY'] = os.environ.get('ENCRYPTION_KEY', None)

# 初始化加密密钥
if not app.config['ENCRYPTION_KEY']:
    key = Fernet.generate_key()
    app.config['ENCRYPTION_KEY'] = key
else:
    key = app.config['ENCRYPTION_KEY']

cipher_suite = Fernet(key)

# 初始化 Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 用户模型
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 创建管理员用户
admin_user = User(
    id=1,
    username=app.config['ADMIN_USERNAME'],
    password_hash=generate_password_hash(app.config['ADMIN_PASSWORD'])
)

@login_manager.user_loader
def load_user(user_id):
    if int(user_id) == 1:
        return admin_user
    return None

# 加密敏感数据
def encrypt_api_key(api_key):
    # 不再加密，直接返回原始值
    return api_key

# 解密敏感数据
def decrypt_api_key(encrypted_api_key):
    # 不再解密，直接返回原始值
    return encrypted_api_key

# 读取配置文件
def read_config():
    config_path = app.config['CONFIG_PATH']
    try:
        if not os.path.exists(config_path):
            # 创建默认配置
            default_config = {
                "USE_MODELSCOPE": "0",
                "PDF2ZH_LANG_FROM": "English",
                "PDF2ZH_LANG_TO": "Simplified Chinese",
                "NOTO_FONT_PATH": "./LXGWWenKai-Regular.ttf",
                "translators": []
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            return default_config
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}")
        return {"error": str(e)}

# 保存配置文件
def save_config(config):
    config_path = app.config['CONFIG_PATH']
    try:
        # 创建备份
        if os.path.exists(config_path):
            backup_path = f"{config_path}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    with open(backup_path, 'w', encoding='utf-8') as bf:
                        bf.write(f.read())
            except Exception as be:
                logger.error(f"创建配置备份失败: {be}")
        
        # 保存新配置(明文)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        return True
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        return False

# 获取配置变更日志
def get_config_history():
    config_dir = os.path.dirname(app.config['CONFIG_PATH'])
    history = []
    
    for filename in os.listdir(config_dir):
        if filename.startswith(os.path.basename(app.config['CONFIG_PATH']) + '.bak.'):
            timestamp = filename.split('.')[-1]
            try:
                dt = datetime.strptime(timestamp, '%Y%m%d%H%M%S')
                history.append({
                    'filename': filename,
                    'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                    'path': os.path.join(config_dir, filename)
                })
            except:
                pass
    
    return sorted(history, key=lambda x: x['datetime'], reverse=True)

# 路由：登录
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == admin_user.username and admin_user.check_password(password):
            login_user(admin_user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('用户名或密码错误', 'danger')
    
    return render_template('login.html')

# 路由：登出
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# 路由：首页
@app.route('/')
@login_required
def index():
    config = read_config()
    history = get_config_history()
    return render_template('index.html', config=config, history=history)

# 路由：更新基本配置
@app.route('/update_basic_config', methods=['POST'])
@login_required
def update_basic_config():
    config = read_config()
    
    # 更新基本配置
    config['USE_MODELSCOPE'] = request.form.get('USE_MODELSCOPE', '0')
    config['PDF2ZH_LANG_FROM'] = request.form.get('PDF2ZH_LANG_FROM', 'English')
    config['PDF2ZH_LANG_TO'] = request.form.get('PDF2ZH_LANG_TO', 'Simplified Chinese')
    config['NOTO_FONT_PATH'] = request.form.get('NOTO_FONT_PATH', './LXGWWenKai-Regular.ttf')
    
    if save_config(config):
        flash('基本配置已更新', 'success')
    else:
        flash('更新配置失败', 'danger')
    
    return redirect(url_for('index'))

# 路由：添加翻译器
@app.route('/add_translator', methods=['POST'])
@login_required
def add_translator():
    translator_name = request.form.get('translator_name')
    
    if not translator_name:
        flash('翻译器名称不能为空', 'danger')
        return redirect(url_for('index'))
    
    config = read_config()
    
    # 确保 translators 存在
    if 'translators' not in config:
        config['translators'] = []
    
    # 检查翻译器是否已存在
    for translator in config['translators']:
        if translator.get('name') == translator_name:
            flash(f'翻译器 {translator_name} 已存在', 'warning')
            return redirect(url_for('index'))
    
    # 添加新翻译器
    new_translator = {
        'name': translator_name,
        'envs': {}
    }
    
    # 处理环境变量
    for key, value in request.form.items():
        if key.startswith('env_key_') and value:
            index = key.replace('env_key_', '')
            env_value = request.form.get(f'env_value_{index}', '')
            new_translator['envs'][value] = env_value
    
    config['translators'].append(new_translator)
    
    if save_config(config):
        flash(f'翻译器 {translator_name} 已添加', 'success')
    else:
        flash('添加翻译器失败', 'danger')
    
    return redirect(url_for('index'))

# 路由：更新翻译器
@app.route('/update_translator/<translator_name>', methods=['POST'])
@login_required
def update_translator(translator_name):
    config = read_config()
    
    # 查找并更新翻译器
    for translator in config.get('translators', []):
        if translator.get('name') == translator_name:
            # 更新环境变量
            translator['envs'] = {}
            for key, value in request.form.items():
                if key.startswith('env_key_') and value:
                    index = key.replace('env_key_', '')
                    env_value = request.form.get(f'env_value_{index}', '')
                    translator['envs'][value] = env_value
            
            if save_config(config):
                flash(f'翻译器 {translator_name} 已更新', 'success')
            else:
                flash('更新翻译器失败', 'danger')
            
            break
    else:
        flash(f'翻译器 {translator_name} 不存在', 'danger')
    
    return redirect(url_for('index'))

# 路由：删除翻译器
@app.route('/delete_translator/<translator_name>', methods=['POST'])
@login_required
def delete_translator(translator_name):
    config = read_config()
    
    # 查找并删除翻译器
    for i, translator in enumerate(config.get('translators', [])):
        if translator.get('name') == translator_name:
            del config['translators'][i]
            
            if save_config(config):
                flash(f'翻译器 {translator_name} 已删除', 'success')
            else:
                flash('删除翻译器失败', 'danger')
            
            break
    else:
        flash(f'翻译器 {translator_name} 不存在', 'danger')
    
    return redirect(url_for('index'))

# 路由：API 获取配置
@app.route('/api/config', methods=['GET'])
def api_get_config():
    config = read_config()
    # 移除敏感信息
    if 'translators' in config:
        for translator in config['translators']:
            if 'envs' in translator:
                for key in translator['envs']:
                    if 'API_KEY' in key:
                        translator['envs'][key] = '******'
    
    return jsonify(config)

# 路由：API 测试连接
@app.route('/api/test_connection', methods=['POST'])
@login_required
def api_test_connection():
    """测试AI翻译API连接"""
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '请求数据无效'}), 400
    
    service_type = data.get('service_type')
    base_url = data.get('base_url')
    api_key = data.get('api_key')
    model = data.get('model')
    
    # 基本验证
    if not service_type or not api_key:
        return jsonify({'status': 'error', 'message': '缺少必要参数'}), 400
    
    try:
        if service_type == 'openai':
            # 测试OpenAI兼容的API接口
            result = test_openai_connection(base_url, api_key, model)
            return jsonify(result)
        else:
            return jsonify({'status': 'error', 'message': f'不支持的服务类型: {service_type}'}), 400
    except Exception as e:
        logger.error(f"API连接测试错误: {str(e)}")
        return jsonify({'status': 'error', 'message': f'连接测试失败: {str(e)}'}), 500

def test_openai_connection(base_url, api_key, model=None):
    """测试OpenAI兼容的API连接"""
    if not base_url:
        base_url = "https://api.openai.com/v1"
    
    if not model:
        model = "gpt-3.5-turbo"  # 默认模型
    
    # 创建临时文件存储curl命令输出
    with tempfile.NamedTemporaryFile(delete=False, mode='w+t') as temp_file:
        try:
            # 构建curl命令
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            data = {
                "model": model,
                "messages": [
                    {"role": "user", "content": "简单的测试问题：你好，世界！"}
                ],
                "max_tokens": 50
            }
            
            # 使用Python请求库直接请求
            try:
                url = f"{base_url.rstrip('/')}/chat/completions"
                logger.info(f"测试连接: {url}")
                
                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=15
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    content = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    
                    return {
                        'status': 'success', 
                        'message': '连接测试成功',
                        'response': content,
                        'model': response_data.get('model', model),
                        'raw_response': response_data
                    }
                else:
                    error_msg = response.json() if response.text else {'error': f'HTTP错误: {response.status_code}'}
                    return {
                        'status': 'error',
                        'message': f'API返回错误: {response.status_code}',
                        'details': error_msg
                    }
            
            except requests.RequestException as e:
                # 如果Python请求失败，尝试使用curl命令
                logger.warning(f"Python请求失败，尝试使用curl: {str(e)}")
                
                curl_cmd = [
                    'curl', '-s', '-X', 'POST',
                    '-H', f'Content-Type: application/json',
                    '-H', f'Authorization: Bearer {api_key}',
                    '-d', json.dumps(data),
                    f'{base_url.rstrip("/")}/chat/completions'
                ]
                
                # 执行curl命令
                result = subprocess.run(curl_cmd, capture_output=True, text=True)
                temp_file.write(result.stdout)
                temp_file.write(result.stderr)
                temp_file.flush()
                
                if result.returncode == 0 and result.stdout:
                    try:
                        response_data = json.loads(result.stdout)
                        content = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
                        
                        return {
                            'status': 'success', 
                            'message': '连接测试成功 (通过curl)',
                            'response': content,
                            'model': response_data.get('model', model),
                            'raw_response': response_data
                        }
                    except json.JSONDecodeError:
                        return {
                            'status': 'error',
                            'message': 'API返回了无效的JSON数据',
                            'details': result.stdout[:500]
                        }
                else:
                    return {
                        'status': 'error',
                        'message': 'curl命令执行失败',
                        'details': result.stderr or result.stdout
                    }
        
        except Exception as e:
            logger.error(f"执行测试请求时出错: {str(e)}")
            return {'status': 'error', 'message': f'连接测试失败: {str(e)}'}
        finally:
            # 清理临时文件
            temp_file_path = temp_file.name
            
    try:
        os.unlink(temp_file_path)
    except:
        pass

# 启动应用
def run_app(host='0.0.0.0', port=8889):
    from waitress import serve
    logger.info(f"配置管理界面启动在 http://{host}:{port}")
    serve(app, host=host, port=port)

if __name__ == '__main__':
    run_app()
