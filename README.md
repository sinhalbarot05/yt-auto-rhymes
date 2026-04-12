# 🎬 YT Auto Rhymes

> **Automated script for Hindi Masti Rhymes YouTube channel**

An intelligent automation tool that generates and uploads Hindi rhyme videos to YouTube automatically. Perfect for content creators looking to scale their video production without manual effort.

---

## ✨ Features

- 🤖 **Fully Automated** - Generate videos without manual intervention
- 🎵 **Hindi Rhyme Generation** - Creates engaging Hindi content automatically
- 📹 **YouTube Integration** - Direct uploads to your YouTube channel
- ⚙️ **Easy Configuration** - Simple setup with API keys
- 🔄 **Scheduled Processing** - Run on a schedule using cron or task scheduler
- 📊 **Logging & Monitoring** - Track all automated processes

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- A YouTube channel
- Google Cloud API credentials
- Internet connection

### Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/sinhalbarot05/yt-auto-rhymes.git
   cd yt-auto-rhymes
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Get Your API Keys** (See setup section below)

4. **Configure Environment Variables**
   ```bash
   cp .env.example .env
   # Edit .env file with your API keys
   ```

5. **Run the Script**
   ```bash
   python main.py
   ```

---

## 🔑 API Setup Guide

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **"Select a Project"** → **"New Project"**
3. Enter project name: `yt-auto-rhymes`
4. Click **"Create"**
5. Wait for the project to be created

### Step 2: Enable YouTube Data API v3

1. In Google Cloud Console, go to **"APIs & Services"** → **"Library"**
2. Search for **"YouTube Data API v3"**
3. Click on it and press **"Enable"**

### Step 3: Create OAuth 2.0 Credentials

1. Go to **"APIs & Services"** → **"Credentials"**
2. Click **"+ Create Credentials"** → **"OAuth 2.0 Client ID"**
3. If prompted, configure the OAuth consent screen first:
   - User Type: **External**
   - Fill in app name, user support email, developer contact
   - Add scopes: `https://www.googleapis.com/auth/youtube.force-ssl`
   - Add test users (your email)
4. For Application Type, select: **Desktop application**
5. Click **"Create"**
6. Download the JSON file
7. Rename it to `credentials.json` and place it in your project root

### Step 4: Get Your API Key

1. In **"Credentials"**, click **"+ Create Credentials"** → **"API Key"**
2. Copy the API key
3. Add it to your `.env` file as `YOUTUBE_API_KEY`

### Step 5: Configure Environment Variables

Create a `.env` file in your project root:

```env
# YouTube API
YOUTUBE_API_KEY=your_api_key_here
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here

# Channel Settings
CHANNEL_ID=your_channel_id_here

# Optional Settings
LOG_LEVEL=INFO
OUTPUT_DIRECTORY=./videos
```

---

## 📋 Configuration

### `.env` File Options

```env
# Required
YOUTUBE_API_KEY=sk-xxxxxxxxxxxxxxxx          # Your YouTube API key
CHANNEL_ID=UC_xxxxxxxxxxxxxxxxxx             # Your YouTube Channel ID

# OAuth (for channel uploads)
YOUTUBE_CLIENT_ID=xxx.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=xxxxx

# Optional
LOG_LEVEL=INFO                               # DEBUG, INFO, WARNING, ERROR
OUTPUT_DIRECTORY=./videos                    # Where to save generated videos
UPLOAD_SCHEDULE=*/6 * * * *                 # Cron format (every 6 hours)
ENABLE_NOTIFICATIONS=true                    # Send completion notifications
```

---

## 📖 Usage

### Basic Usage

```bash
python main.py
```

### Generate Videos Only (No Upload)

```bash
python main.py --generate-only
```

### Upload Existing Videos

```bash
python main.py --upload-only
```

### View Logs

```bash
tail -f logs/yt-auto-rhymes.log
```

---

## 🔄 Scheduling (Optional)

### On Linux/macOS (Using Cron)

1. Open crontab editor:
   ```bash
   crontab -e
   ```

2. Add this line to run every 6 hours:
   ```bash
   0 */6 * * * cd /path/to/yt-auto-rhymes && python main.py >> logs/cron.log 2>&1
   ```

3. Save and exit (Ctrl+X, then Y, then Enter)

### On Windows (Using Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task → Name: `YT Auto Rhymes`
3. Set trigger: Repeat every 6 hours
4. Set action: Start a program
5. Program: `python.exe`
6. Arguments: `C:\path\to\yt-auto-rhymes\main.py`

---

## 🛠️ Troubleshooting

### Issue: "Invalid API Key"
- ✅ Check that you copied the API key correctly from Google Cloud Console
- ✅ Verify the API key is in your `.env` file
- ✅ Ensure YouTube Data API v3 is enabled

### Issue: "Authentication Failed"
- ✅ Delete `token.json` file and re-authenticate
- ✅ Check that `credentials.json` is in the project root
- ✅ Verify OAuth credentials are correct

### Issue: "Quota Exceeded"
- ✅ YouTube API has daily quotas
- ✅ Check your usage in Google Cloud Console
- ✅ Consider requesting quota increase

### Issue: "Video Upload Failed"
- ✅ Ensure your channel allows automated uploads
- ✅ Check video file format and size
- ✅ Verify channel ID is correct

---

## 📚 Project Structure

```
yt-auto-rhymes/
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── config/
│   └── settings.py        # Configuration settings
├── core/
│   ├── generator.py       # Video generation logic
│   ├── uploader.py        # YouTube upload logic
│   └── api_client.py      # YouTube API wrapper
├── logs/
│   └── yt-auto-rhymes.log # Application logs
├── videos/
│   └── [generated videos] # Output directory
└── README.md              # This file
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues and enhancement requests.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## ⚠️ Disclaimer

- Respect YouTube's Terms of Service and Community Guidelines
- Ensure you have rights to all content generated
- Use responsibly and ethically
- This tool is for educational and authorized use only

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 📞 Support

For issues, questions, or feature requests:
- 📧 Email: [your.email@example.com]
- 🐛 GitHub Issues: [Create an issue](https://github.com/sinhalbarot05/yt-auto-rhymes/issues)
- 💬 Discussions: [Join discussions](https://github.com/sinhalbarot05/yt-auto-rhymes/discussions)

---

## 🙏 Acknowledgments

- Built with ❤️ for content creators
- Powered by [YouTube API v3](https://developers.google.com/youtube/v3)
- Special thanks to the open-source community

---

**Made with ❤️ by SINHAL BAROT**
