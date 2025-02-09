from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, MessageMediaPhoto, MessageMediaDocument
from telethon.tl.types import UserStatusOnline, UserStatusOffline, UserStatusRecently
from telethon.utils import get_display_name
import csv, os, json, re, emoji
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from rich.console import Console
from rich.progress import track
from rich.table import Table
import pandas as pd
import networkx as nx
from textblob import TextBlob
import matplotlib.pyplot as plt
from urllib.parse import urlparse
import asyncio
import logging
from pathlib import Path

class TelegramAnalyzer:
    def __init__(self, api_id, api_hash, phone):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.client = TelegramClient(phone, api_id, api_hash)
        self.console = Console()
        self.output_dir = "telegram_analysis"
        Path(self.output_dir).mkdir(exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            filename=f'{self.output_dir}/analysis.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    async def initialize(self):
        """Initialize the client and connect"""
        try:
            await self.client.start()
            if not await self.client.is_user_authorized():
                await self.client.send_code_request(self.phone)
                code = input('Enter the code: ')
                await self.client.sign_in(self.phone, code)
            return True
        except Exception as e:
            self.logger.error(f"Initialization error: {str(e)}")
            return False

    async def analyze_group(self, group):
        """Complete group analysis"""
        group_dir = f"{self.output_dir}/{self._clean_filename(group.title)}"
        Path(group_dir).mkdir(exist_ok=True)
        
        self.console.print(f"\n[bold green]Starting analysis for {group.title}[/bold green]")
        
        try:
            # Basic member data
            members_data = await self._get_members_data(group)
            
            # Message analysis
            messages_data = await self._analyze_messages(group)
            
            # Media analysis
            media_data = await self._analyze_media(group)
            
            # Network analysis
            network_data = await self._analyze_network(group)
            
            # Content analysis
            content_data = await self._analyze_content(group)
            
            # Save all analyses
            await self._save_analysis(group_dir, {
                'members': members_data,
                'messages': messages_data,
                'media': media_data,
                'network': network_data,
                'content': content_data
            })
            
            # Generate visualizations
            await self._generate_visualizations(group_dir, {
                'messages': messages_data,
                'network': network_data,
                'content': content_data
            })
            
        except Exception as e:
            self.logger.error(f"Error analyzing group {group.title}: {str(e)}")
            self.console.print(f"[red]Error during analysis: {str(e)}[/red]")

    async def _get_members_data(self, group):
        """Get detailed member information"""
        members_data = []
        
        async for user in self.client.iter_participants(group):
            try:
                member = {
                    'id': user.id,
                    'username': user.username,
                    'name': get_display_name(user),
                    'phone': user.phone if hasattr(user, 'phone') else None,
                    'bio': await self._get_user_bio(user),
                    'profile_photo': await self._get_profile_photo_info(user),
                    'status': self._get_user_status(user),
                    'joined_date': self._get_join_date(user),
                    'is_bot': user.bot if hasattr(user, 'bot') else False,
                    'is_verified': user.verified if hasattr(user, 'verified') else False,
                    'common_chats': await self._get_common_chats(user)
                }
                members_data.append(member)
            except Exception as e:
                self.logger.warning(f"Error processing user {user.id}: {str(e)}")
                
        return members_data

    async def _analyze_messages(self, group):
        """Analyze message patterns and activity"""
        message_data = {
            'activity_hours': defaultdict(int),
            'activity_days': defaultdict(int),
            'user_activity': defaultdict(int),
            'reply_patterns': defaultdict(list),
            'forward_patterns': defaultdict(int),
            'reactions': defaultdict(lambda: defaultdict(int)),
            'message_types': defaultdict(int)
        }
        
        async for message in self.client.iter_messages(group, limit=None):
            try:
                # Time analysis
                if message.date:
                    message_data['activity_hours'][message.date.hour] += 1
                    message_data['activity_days'][message.date.strftime('%A')] += 1
                
                # User activity
                if message.sender_id:
                    message_data['user_activity'][message.sender_id] += 1
                
                # Reply patterns
                if message.reply_to:
                    message_data['reply_patterns'][message.sender_id].append(message.reply_to.reply_to_msg_id)
                
                # Forwards
                if message.forward:
                    message_data['forward_patterns'][message.forward.from_id] += 1
                
                # Reactions
                if message.reactions:
                    for reaction in message.reactions.results:
                        message_data['reactions'][message.sender_id][reaction.reaction] += 1
                
                # Message types
                message_data['message_types'][type(message.media).__name__ if message.media else 'text'] += 1
                
            except Exception as e:
                self.logger.warning(f"Error processing message: {str(e)}")
                
        return message_data

    async def _analyze_media(self, group):
        """Analyze media content"""
        media_data = {
            'photos': [],
            'videos': [],
            'files': [],
            'links': [],
            'voice_messages': [],
            'stickers': []
        }
        
        async for message in self.client.iter_messages(group, limit=None):
            try:
                if message.media:
                    if isinstance(message.media, MessageMediaPhoto):
                        media_data['photos'].append({
                            'id': message.id,
                            'date': message.date.isoformat(),
                            'sender_id': message.sender_id,
                            'file_size': message.file.size if message.file else None
                        })
                    elif isinstance(message.media, MessageMediaDocument):
                        if message.media.document.mime_type.startswith('video'):
                            media_data['videos'].append({
                                'id': message.id,
                                'date': message.date.isoformat(),
                                'sender_id': message.sender_id,
                                'file_size': message.file.size if message.file else None,
                                'duration': getattr(message.media.document.attributes[0], 'duration', None)
                            })
                        elif message.media.document.mime_type.startswith('audio'):
                            media_data['voice_messages'].append({
                                'id': message.id,
                                'date': message.date.isoformat(),
                                'sender_id': message.sender_id,
                                'duration': getattr(message.media.document.attributes[0], 'duration', None)
                            })
                
                # Extract links
                if message.text:
                    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', 
                                    message.text)
                    for url in urls:
                        media_data['links'].append({
                            'url': url,
                            'domain': urlparse(url).netloc,
                            'sender_id': message.sender_id,
                            'date': message.date.isoformat()
                        })
                        
            except Exception as e:
                self.logger.warning(f"Error processing media: {str(e)}")
                
        return media_data

    async def _analyze_network(self, group):
        """Analyze user interaction network"""
        network_data = {
            'interactions': [],
            'user_centrality': {},
            'communities': [],
            'influence_scores': {}
        }
        
        # Create a network graph
        G = nx.Graph()
        
        async for message in self.client.iter_messages(group, limit=None):
            try:
                if message.reply_to:
                    network_data['interactions'].append({
                        'from_user': message.sender_id,
                        'to_user': message.reply_to.reply_to_msg_id,
                        'type': 'reply',
                        'date': message.date.isoformat()
                    })
                    G.add_edge(message.sender_id, message.reply_to.reply_to_msg_id)
                    
            except Exception as e:
                self.logger.warning(f"Error in network analysis: {str(e)}")
        
        # Calculate network metrics
        try:
            network_data['user_centrality'] = nx.degree_centrality(G)
            network_data['communities'] = list(nx.community.greedy_modularity_communities(G))
            network_data['influence_scores'] = nx.pagerank(G)
        except Exception as e:
            self.logger.warning(f"Error calculating network metrics: {str(e)}")
            
        return network_data

    async def _analyze_content(self, group):
        """Analyze message content"""
        content_data = {
            'hashtags': Counter(),
            'mentions': Counter(),
            'keywords': Counter(),
            'languages': Counter(),
            'sentiment': defaultdict(list),
            'emoji_usage': Counter()
        }
        
        async for message in self.client.iter_messages(group, limit=None):
            try:
                if message.text:
                    # Hashtags and mentions
                    hashtags = re.findall(r'#\w+', message.text)
                    mentions = re.findall(r'@\w+', message.text)
                    content_data['hashtags'].update(hashtags)
                    content_data['mentions'].update(mentions)
                    
                    # Keywords (simple implementation)
                    words = message.text.lower().split()
                    content_data['keywords'].update(words)
                    
                    # Language detection
                    try:
                        blob = TextBlob(message.text)
                        content_data['languages'][blob.detect_language()] += 1
                    except:
                        pass
                    
                    # Sentiment analysis
                    try:
                        sentiment = TextBlob(message.text).sentiment.polarity
                        content_data['sentiment'][message.sender_id].append(sentiment)
                    except:
                        pass
                    
                    # Emoji analysis
                    emojis = [c for c in message.text if c in emoji.EMOJI_DATA]
                    content_data['emoji_usage'].update(emojis)
                    
            except Exception as e:
                self.logger.warning(f"Error in content analysis: {str(e)}")
                
        return content_data

    async def _save_analysis(self, output_dir, data):
        """Save analysis results"""
        try:
            # Save each analysis type to separate files
            for analysis_type, analysis_data in data.items():
                output_file = f"{output_dir}/{analysis_type}_analysis.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(analysis_data, f, ensure_ascii=False, indent=4, default=str)
                    
            self.console.print(f"[green]Analysis saved to {output_dir}[/green]")
            
        except Exception as e:
            self.logger.error(f"Error saving analysis: {str(e)}")

    async def _generate_visualizations(self, output_dir, data):
        """Generate visualization charts"""
        try:
            # Activity patterns
            plt.figure(figsize=(12, 6))
            hours = data['messages']['activity_hours']
            plt.bar(hours.keys(), hours.values())
            plt.title('Message Activity by Hour')
            plt.savefig(f"{output_dir}/activity_hours.png")
            plt.close()
            
            # Network graph
            if data['network']['interactions']:
                G = nx.Graph()
                for interaction in data['network']['interactions']:
                    G.add_edge(interaction['from_user'], interaction['to_user'])
                    
                plt.figure(figsize=(12, 12))
                nx.draw(G, with_labels=True, node_color='lightblue', 
                       node_size=500, font_size=8)
                plt.title('User Interaction Network')
                plt.savefig(f"{output_dir}/network_graph.png")
                plt.close()
                
            # Word cloud of hashtags
            if data['content']['hashtags']:
                from wordcloud import WordCloud
                wordcloud = WordCloud(width=800, height=400, 
                                    background_color='white').generate_from_frequencies(
                                        data['content']['hashtags'])
                plt.figure(figsize=(10, 5))
                plt.imshow(wordcloud, interpolation='bilinear')
                plt.axis('off')
                plt.title('Hashtag Cloud')
                plt.savefig(f"{output_dir}/hashtag_cloud.png")
                plt.close()
                
        except Exception as e:
            self.logger.error(f"Error generating visualizations: {str(e)}")

    @staticmethod
    def _clean_filename(filename):
        """Clean filename for saving"""
        return "".join(x for x in filename if x.isalnum() or x in (' ', '-', '_')).rstrip()

    # Helper methods for user data
    async def _get_user_bio(self, user):
        try:
            full = await self.client.get_entity(user.id)
            return full.about if hasattr(full, 'about') else None
        except:
            return None

    async def _get_profile_photo_info(self, user):
        try:
            photos = await self.client.get_profile_photos(user)
            return {
                'has_photo': bool(photos.total),
                'total_photos': photos.total
            }
        except:
            return {'has_photo': False, 'total_photos': 0}

    @staticmethod
    def _get_user_status(user):
        if not hasattr(user, 'status'):
            return "Unknown"
        elif isinstance(user.status, UserStatusOnline):
            return "Online"
        elif isinstance(user.status, UserStatusOffline):
            return f"Last seen: {user.status.was_online}"
        elif isinstance(user.status, UserStatusRecently):
            return "Recently"
        return "Unknown"

    @staticmethod
    def _get_join_date(user):
        try:
            return user.participant.date.isoformat() if hasattr(user, 'participant') else None
        except:
            return None

    async def _get_common_chats(self, user):
        try:
            common = await self.client.get_common_chats(user)
            return [{'id': chat.id, 'title': chat.title} for chat in common]
        except:
            return []

    async def generate_report(self, group_dir):
        """Generate a comprehensive HTML report"""
        try:
            report_data = {}
            
            # Load all analysis files
            for analysis_type in ['members', 'messages', 'media', 'network', 'content']:
                file_path = f"{group_dir}/{analysis_type}_analysis.json"
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        report_data[analysis_type] = json.load(f)

            # Generate HTML report
            html_content = self._generate_html_report(report_data)
            
            # Save report
            with open(f"{group_dir}/analysis_report.html", 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            self.console.print(f"[green]Report generated: {group_dir}/analysis_report.html[/green]")
            
        except Exception as e:
            self.logger.error(f"Error generating report: {str(e)}")

    def _generate_html_report(self, data):
        """Generate HTML report content"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Telegram Group Analysis Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 20px; border: 1px solid #ddd; }}
                .chart {{ width: 100%; max-width: 800px; margin: 20px 0; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f5f5f5; }}
            </style>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        </head>
        <body>
            <h1>Telegram Group Analysis Report</h1>
            
            <div class="section">
                <h2>Member Statistics</h2>
                <p>Total Members: {len(data.get('members', []))}</p>
                {self._generate_member_stats_html(data.get('members', []))}
            </div>

            <div class="section">
                <h2>Activity Analysis</h2>
                {self._generate_activity_stats_html(data.get('messages', {}))}
            </div>

            <div class="section">
                <h2>Media Analysis</h2>
                {self._generate_media_stats_html(data.get('media', {}))}
            </div>

            <div class="section">
                <h2>Network Analysis</h2>
                {self._generate_network_stats_html(data.get('network', {}))}
            </div>

            <div class="section">
                <h2>Content Analysis</h2>
                {self._generate_content_stats_html(data.get('content', {}))}
            </div>
        </body>
        </html>
        """
        return html

    def _generate_member_stats_html(self, members_data):
        """Generate HTML for member statistics"""
        if not members_data:
            return "<p>No member data available</p>"

        # Calculate statistics
        total_members = len(members_data)
        verified_count = sum(1 for m in members_data if m.get('is_verified', False))
        bot_count = sum(1 for m in members_data if m.get('is_bot', False))
        
        return f"""
            <table>
                <tr>
                    <th>Metric</th>
                    <th>Value</th>
                </tr>
                <tr>
                    <td>Total Members</td>
                    <td>{total_members}</td>
                </tr>
                <tr>
                    <td>Verified Members</td>
                    <td>{verified_count}</td>
                </tr>
                <tr>
                    <td>Bots</td>
                    <td>{bot_count}</td>
                </tr>
            </table>
        """

    def _generate_activity_stats_html(self, message_data):
        """Generate HTML for activity statistics"""
        if not message_data:
            return "<p>No activity data available</p>"

        hours_data = message_data.get('activity_hours', {})
        days_data = message_data.get('activity_days', {})

        return f"""
            <div id="hourlyActivity"></div>
            <div id="dailyActivity"></div>
            <script>
                var hourlyData = {{
                    x: {list(hours_data.keys())},
                    y: {list(hours_data.values())},
                    type: 'bar',
                    name: 'Hourly Activity'
                }};

                var dailyData = {{
                    x: {list(days_data.keys())},
                    y: {list(days_data.values())},
                    type: 'bar',
                    name: 'Daily Activity'
                }};

                Plotly.newPlot('hourlyActivity', [hourlyData], {{
                    title: 'Message Activity by Hour'
                }});

                Plotly.newPlot('dailyActivity', [dailyData], {{
                    title: 'Message Activity by Day'
                }});
            </script>
        """

async def main():
    # Your credentials
    API_ID = ''
    API_HASH = ''
    PHONE = '+(COUNTRYCODE)'

    # Initialize analyzer
    analyzer = TelegramAnalyzer(API_ID, API_HASH, PHONE)
    
    # Connect to Telegram
    if not await analyzer.initialize():
        print("Failed to initialize. Exiting...")
        return

    # Get all groups
    groups = await analyzer.client.get_dialogs()
    print("\nAvailable groups:")
    for i, dialog in enumerate(groups):
        if dialog.is_group:
            print(f"{i}. {dialog.title}")

    # Get user input
    while True:
        try:
            group_num = int(input("\nEnter group number to analyze (or -1 to exit): "))
            if group_num == -1:
                break
                
            selected_group = groups[group_num]
            if not selected_group.is_group:
                print("Selected dialog is not a group. Please select a group.")
                continue

            # Perform analysis
            await analyzer.analyze_group(selected_group)
            
            # Generate report
            group_dir = f"{analyzer.output_dir}/{analyzer._clean_filename(selected_group.title)}"
            await analyzer.generate_report(group_dir)
            
        except ValueError:
            print("Please enter a valid number")
        except IndexError:
            print("Please enter a valid group number")
        except Exception as e:
            print(f"An error occurred: {str(e)}")

    # Cleanup
    await analyzer.client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
