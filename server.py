from flask import Flask, request, jsonify, render_template, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configuration de la base de données
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
    audio_filename = db.Column(db.String(200), nullable=True)
    status = db.Column(db.Boolean, default=False)  # False = not completed, True = completed
    completion_date = db.Column(db.DateTime, nullable=True)
    completed_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

@app.route('/')
def index():
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
        if new_text:
            text_audio = TextAudio(text=new_text)
            db.session.add(text_audio)
            db.session.commit()
            return redirect(url_for('data'))
    
    texts = TextAudio.query.order_by(TextAudio.created_at.desc()).all()
    return render_template('data.html', texts=texts)

@app.route('/upload', methods=['POST'])
def upload_audio():
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        text_id = request.form.get('text_id')
        completed_by = request.form.get('completed_by', 'Anonymous')
        
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

        # Mettre à jour la base de données
        text_audio = TextAudio.query.get(text_id)
        if text_audio:
            text_audio.audio_filename = filename
            text_audio.status = True
            text_audio.completion_date = datetime.utcnow()
            text_audio.completed_by = completed_by
            db.session.commit()

        return jsonify({
            'message': 'Audio uploaded successfully',
            'filename': filename,
            'size': len(audio_data)
        }), 200

    except Exception as e:
        print(f"Erreur lors de l'upload: {str(e)}")
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

if __name__ == '__main__':
    app.run(debug=True)