from flask import Flask, request, jsonify, render_template, redirect, url_for, send_from_directory, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from datetime import datetime
import json
from werkzeug.utils import secure_filename
import csv
from io import BytesIO, TextIOWrapper

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = 'votre_clé_secrète_ici'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = 'uploads'  # Définir le dossier d'upload
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Assurez-vous que le dossier uploads existe
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# Modèle de base de données
class TextAudio(db.Model):
    __tablename__ = 'text_audio'
    
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    theme = db.Column(db.String(100), nullable=True)
    answer = db.Column(db.String(500), nullable=True)
    audio_filename = db.Column(db.String(200), nullable=True)
    status = db.Column(db.Boolean, default=False)  # False = not completed, True = completed
    completion_date = db.Column(db.DateTime, nullable=True)
    completed_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    consent_date = db.Column(db.DateTime, nullable=True)
    consent_version = db.Column(db.String(10), nullable=True)
    consent_ip = db.Column(db.String(45), nullable=True)
    consent_user_agent = db.Column(db.String(500), nullable=True)

    def __repr__(self):
        return f'<TextAudio {self.id}>'

# Supprimer la base de données existante et en créer une nouvelle
def reset_database():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Base de données réinitialisée avec succès!")

# Créer la base de données
with app.app_context():
    db.create_all()
    print("Tables créées avec succès!")

# Script de migration (à exécuter une seule fois)
def migrate_data():
    with app.app_context():
        # Sauvegarder les anciennes données
        old_records = TextAudio.query.all()
        old_data = [(record.text, record.audio_filename) for record in old_records]
        
        # Réinitialiser la base de données
        db.drop_all()
        db.create_all()
        
        # Restaurer les données avec le nouveau schéma
        for text, audio_filename in old_data:
            new_record = TextAudio(
                text=text,
                audio_filename=audio_filename,
                status=False,
                created_at=datetime.utcnow()
            )
            db.session.add(new_record)
        
        db.session.commit()
        print("Migration terminée avec succès!")

# Add this near the top of your file with other configurations
PREDEFINED_THEMES = [
    "Science",
    "History",
    "Literature",
    "Geography",
    "Mathematics",
    "Technology",
    "Arts",
    "Music",
    "Sports",
    "Current Events",
    "Philosophy",
    "Economics",
    "Psychology",
    "Biology",
    "Physics",
    "Chemistry"
]

@app.route('/')
def index():
    # Check if user has given consent
    if 'consent' not in session:
        return redirect(url_for('consent'))
        
    text_audio = TextAudio.query.filter_by(status=False).first()
    
    # Obtenir les statistiques
    total_texts = TextAudio.query.count()
    completed_texts = TextAudio.query.filter_by(status=True).count()
    
    return render_template('index.html', 
                         text_audio=text_audio,
                         completed_texts=completed_texts,
                         total_texts=total_texts)

@app.route('/data', methods=['GET', 'POST'])
def data():
    if request.method == 'POST':
        new_text = request.form.get('text')
        new_theme = request.form.get('theme')
        new_answer = request.form.get('answer')
        if new_text:
            text_audio = TextAudio(
                text=new_text,
                theme=new_theme,
                answer=new_answer
            )
            db.session.add(text_audio)
            db.session.commit()
            flash('Text added successfully!', 'success')
        return redirect(url_for('data'))
    
    # Get sorting parameters from URL
    sort_column = request.args.get('sort', 'id')  # default sort by id
    sort_direction = request.args.get('direction', 'asc')  # default ascending
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 5, type=int)
    
    # Create the base query
    query = TextAudio.query

    # Apply sorting based on column
    if sort_column == 'id':
        order_by = TextAudio.id
    elif sort_column == 'theme':
        order_by = TextAudio.theme
    elif sort_column == 'text':
        order_by = TextAudio.text
    elif sort_column == 'answer':
        order_by = TextAudio.answer
    elif sort_column == 'status':
        order_by = TextAudio.status
    elif sort_column == 'completed_by':
        order_by = TextAudio.completed_by
    elif sort_column == 'completion_date':
        order_by = TextAudio.completion_date
    else:
        order_by = TextAudio.id  # fallback to id

    # Apply sort direction
    if sort_direction == 'desc':
        order_by = order_by.desc()
    
    # Get paginated and sorted results
    pagination = query.order_by(order_by).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('data.html', 
                         pagination=pagination,
                         texts=pagination.items,
                         themes=PREDEFINED_THEMES,
                         current_sort=sort_column,
                         current_direction=sort_direction,
                         current_per_page=per_page)

@app.route('/upload', methods=['POST'])
def upload_audio():
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        text_id = request.form.get('text_id')
        completed_by = request.form.get('completed_by', 'Anonymous')
        print("Completed by:", completed_by)
        
        audio = request.files['audio']
        if audio.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        # Vérifier la taille du fichier
        audio_data = audio.read()
        if len(audio_data) == 0:
            return jsonify({'error': 'Empty audio file'}), 400
            
        # Créer le dossier uploads s'il n'existe pas
        if not os.path.exists('uploads'):
            os.makedirs('uploads')
        
        # Générer le nom du fichier
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audio_{timestamp}.wav"
        
        # Sauvegarder le fichier
        with open(os.path.join('uploads', filename), 'wb') as f:
            f.write(audio_data)

        # Get consent information from session
        consent_info = session.get('consent')
        if not consent_info:
            return jsonify({'error': 'No consent information found'}), 403

        # Update the database record with consent information
        text_audio = TextAudio.query.get(text_id)
        if text_audio:
            text_audio.audio_filename = filename
            text_audio.status = True
            text_audio.completion_date = datetime.utcnow()
            text_audio.completed_by = completed_by
            
            # Add consent information
            text_audio.consent_date = consent_info['date']
            text_audio.consent_version = consent_info['version']
            text_audio.consent_ip = consent_info['ip']
            text_audio.consent_user_agent = consent_info['user_agent']
            
            db.session.commit()

        return jsonify({
            'message': 'Audio uploaded successfully',
            'filename': filename,
            'size': len(audio_data)
        }), 200

    except Exception as e:
        print(f"Error during upload: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/next_text', methods=['GET'])
def next_text():
    current_id = request.args.get('current_id', type=int)
    
    # D'abord, essayez de trouver le prochain texte non complété
    next_text = TextAudio.query.filter(
        TextAudio.id > current_id, 
        TextAudio.status == False
    ).order_by(TextAudio.id).first()
    
    # Si aucun texte n'est trouvé après l'ID actuel, revenez au début
    if not next_text:
        next_text = TextAudio.query.filter(
            TextAudio.status == False
        ).order_by(TextAudio.id).first()

    if next_text:
        return jsonify({
            'id': next_text.id, 
            'text': next_text.text,
            'wrapped': next_text.id < current_id  # Indique si on est revenu au début
        })
    else:
        return jsonify({'error': 'No texts available'}), 404

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload_jsonl', methods=['POST'])
def upload_jsonl():
    if 'jsonl_file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('data'))
    
    file = request.files['jsonl_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('data'))

    try:
        content = file.read().decode('utf-8')
        lines = content.strip().split('\n')
        
        success_count = 0
        error_count = 0
        
        for line in lines:
            try:
                data = json.loads(line.strip())
                
                if 'text' not in data:
                    error_count += 1
                    continue
                
                text_audio = TextAudio(
                    text=data['text'],
                    theme=data.get('theme', None),
                    answer=data.get('answer', None)
                )
                db.session.add(text_audio)
                success_count += 1
                
            except json.JSONDecodeError:
                error_count += 1
                continue
        
        db.session.commit()
        flash(f'Successfully added {success_count} texts. {error_count} errors.', 'success')
        
    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'error')
    
    return redirect(url_for('data'))

@app.route('/consent')
def consent():
    return render_template('consent.html')

@app.route('/submit_consent', methods=['POST'])
def submit_consent():
    try:
        # Get user information using the new helper function
        user_ip = get_client_ip()
        user_agent = request.headers.get('User-Agent')
        consent_version = request.form.get('consent_version', '1.0')
        consent_date = datetime.utcnow()
        
        # Store consent in session
        session['consent'] = {
            'date': consent_date,
            'version': consent_version,
            'ip': user_ip,
            'user_agent': user_agent
        }
        
        return redirect(url_for('index'))
    except Exception as e:
        flash('Error processing consent: ' + str(e), 'error')
        return redirect(url_for('consent'))

def get_client_ip():
    """Get the real client IP address considering various proxy headers"""
    # Check X-Forwarded-For header first (used by most proxies)
    if 'X-Forwarded-For' in request.headers:
        # Get the first IP in the chain (real client IP)
        return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    
    # Check other common headers
    if 'X-Real-IP' in request.headers:
        return request.headers.get('X-Real-IP')
    
    # If no proxy headers found, use the direct client IP
    return request.remote_addr

@app.route('/export/<format>')
def export_data(format):
    # Get all texts
    texts = TextAudio.query.all()
    
    # Convert texts to dictionary format
    data = [{
        'id': text.id,
        'text': text.text,
        'theme': text.theme,
        'answer': text.answer,
        'status': text.status,
        'audio_filename': text.audio_filename,
        'completed_by': text.completed_by,
        'completion_date': text.completion_date.isoformat() if text.completion_date else None,
        'consent_date': text.consent_date.isoformat() if text.consent_date else None,
        'consent_version': text.consent_version,
    } for text in texts]
    
    if format == 'json':
        # Export as JSON
        output = json.dumps(data, indent=2)
        bytes_io = BytesIO(output.encode('utf-8'))
        return send_file(
            bytes_io,
            mimetype='application/json',
            as_attachment=True,
            download_name='texts_export.json'
        )
        
    elif format == 'jsonl':
        # Export as JSONL (JSON Lines)
        output = '\n'.join(json.dumps(item) for item in data)
        bytes_io = BytesIO(output.encode('utf-8'))
        return send_file(
            bytes_io,
            mimetype='application/x-jsonlines',
            as_attachment=True,
            download_name='texts_export.jsonl'
        )
        
    elif format == 'csv':
        # Export as CSV
        output = BytesIO()
        if data:
            # Write the BOM for Excel compatibility
            output.write(b'\xef\xbb\xbf')
            
            # Create a text wrapper around the BytesIO buffer
            text_output = TextIOWrapper(output, encoding='utf-8', newline='')
            
            writer = csv.DictWriter(text_output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            
            # Detach the text wrapper to get back the BytesIO
            text_output.detach()
            
            # Move cursor to the beginning of the buffer
            output.seek(0)
            
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name='texts_export.csv'
        )
    
    else:
        return jsonify({'error': 'Invalid format'}), 400

if __name__ == '__main__':
    app.run(debug=True)