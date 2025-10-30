# Bot Discord

Petit bot Discord développé pour les besoins du cours Web (projet local).

## Description
Bot simple pour automatiser des tâches sur un serveur Discord : commandes textuelles, réponses automatiques et gestion basique d'événements. Conçu pour être modifié et étendu.

## Prérequis
- Node.js (recommandé ≥ 16.9)
- npm ou yarn
- Un bot Discord créé dans le Developer Portal (token et client ID)
- Intents activés selon les fonctionnalités (GUILDS, GUILD_MESSAGES, MESSAGE_CONTENT si nécessaire)

## Installation
1. Cloner le dépôt ou copier les fichiers dans votre dossier de travail.
2. Installer les dépendances :
    - npm:
      npm install
    - yarn:
      yarn

## Configuration
Créer un fichier `.env` à la racine contenant au minimum :
```
DISCORD_TOKEN=your_bot_token
CLIENT_ID=your_client_id
GUILD_ID=your_guild_id   # optionnel pour le déploiement de commandes en local
PREFIX=!
```

Activer les intents nécessaires dans le Developer Portal et dans le code (ex. GUILDS, GUILD_MESSAGES, MESSAGE_CONTENT).

## Démarrage
- Mode production :
  npm start
- Mode développement (avec reload si configuré) :
  npm run dev

Adapter les scripts dans `package.json` si besoin.

## Utilisation
- Préfix par défaut : `!` (modifiable via .env ou configuration)
- Exemple de commandes (à implémenter selon le projet) :
  - `!ping` — réponse "Pong" et latence
  - `!help` — liste des commandes
  - `!say <message>` — fait dire quelque chose au bot

## Déploiement des commandes (slash)
Si vous utilisez des commandes slash, exécutez le script de déploiement :
- npm run deploy-commands
(Assurez-vous d'avoir CLIENT_ID et GUILD_ID si vous faites un déploiement "guild-only" pour tests rapides.)

## Développement
- Structure conseillée :
  - src/ : code source (boutons, événements, commandes)
  - config/ : configuration et constantes
  - scripts/ : déploiement de commandes
- Tester localement sur un serveur de test avant mise en production.

## Sécurité
- Ne jamais committer le token du bot dans le dépôt.
- Utiliser `.gitignore` pour exclure `.env`.

## Contribution
- Forkez le dépôt, créez une branche, puis proposez une PR.
- Respecter les conventions de code et documenter les nouvelles commandes.

## Licence
Ajouter la licence souhaitée (ex. MIT) dans un fichier LICENSE.

## Ressources utiles
- Discord Developer Portal : https://discord.com/developers
- discord.js (si utilisé) : https://discord.js.org

---  
Pour toute question, ouvrir une issue ou contacter le mainteneur du projet.