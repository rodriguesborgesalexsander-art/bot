import discord
from discord.ext import commands
from discord.ui import Button, View
import sqlite3
import random
import asyncio
import time
import os
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', 1494428879362724090))
VERIFY_ROLE_ID = int(os.getenv('VERIFY_ROLE_ID', 1496483129500897352))

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot online!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

conn = sqlite3.connect('verification.db')
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS verified_users (user_id TEXT PRIMARY KEY, username TEXT, verified_at REAL)')
cursor.execute('CREATE TABLE IF NOT EXISTS pending_codes (user_id TEXT PRIMARY KEY, codigo TEXT, expires_at REAL)')
conn.commit()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

class VerifyButton(Button):
    def __init__(self):
        super().__init__(
            label="Iniciar Verificação",
            style=discord.ButtonStyle.danger,
            custom_id="verify_button"
        )
    
    async def callback(self, interaction):
        user_id = str(interaction.user.id)
        
        # Verifica se já está verificado
        cursor.execute("SELECT * FROM verified_users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            embed = discord.Embed(
                title="Acesso já liberado",
                description=f"**{interaction.user.display_name}**, sua conta já está verificada e possui acesso a todos os canais do servidor.",
                color=0xDC2626
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Verifica se tem código pendente
        cursor.execute("SELECT expires_at FROM pending_codes WHERE user_id = ?", (user_id,))
        pending = cursor.fetchone()
        
        if pending:
            expires_at = pending[0]
            if time.time() < expires_at:
                remaining = int(expires_at - time.time())
                embed = discord.Embed(
                    title="Verificação em andamento",
                    description=f"**{interaction.user.display_name}**, você já possui um código de verificação ativo.\n\nDigite o código que foi enviado anteriormente no chat para concluir a verificação.\n\n**Tempo restante:** {remaining} segundos",
                    color=0xDC2626
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            else:
                # Remove código expirado
                cursor.execute("DELETE FROM pending_codes WHERE user_id = ?", (user_id,))
                conn.commit()
        
        # Gera código de 6 dígitos
        codigo = str(random.randint(100000, 999999))
        
        # Salva código pendente (expira em 3 minutos)
        cursor.execute("INSERT OR REPLACE INTO pending_codes (user_id, codigo, expires_at) VALUES (?, ?, ?)",
                      (user_id, codigo, time.time() + 180))
        conn.commit()
        
        # Envia embed com o código
        embed = discord.Embed(
            title="Verificação em Andamento",
            description=f"**{interaction.user.display_name}**, utilize o código abaixo para concluir sua verificação:",
            color=0xDC2626
        )
        embed.add_field(
            name="Código de Verificação",
            value=f"```\n{codigo}\n```",
            inline=False
        )
        embed.add_field(
            name="Instruções",
            value="Digite o código exatamente como aparece neste canal de texto para finalizar a verificação.\n\n"
                  "O código é pessoal e será apagado automaticamente após a verificação.",
            inline=False
        )
        embed.set_footer(text="Você tem 3 minutos para digitar o código")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def send_welcome_message(member, guild_name):
    """Envia mensagem de boas-vindas na DM do membro"""
    embed = discord.Embed(
        title="Bem-vindo ao Servidor!",
        description=f"**{member.display_name}**, sua conta foi verificada com sucesso no servidor **{guild_name}**.",
        color=0x10B981
    )
    
    embed.add_field(
        name="O que você pode fazer agora?",
        value="• Acessar todos os canais do servidor\n"
              "• Participar das conversas\n"
              "• Interagir com outros membros\n"
              "• Receber atualizações e novidades",
        inline=False
    )
    
    embed.add_field(
        name="Regras do Servidor",
        value="Lembre-se de respeitar as regras do servidor para manter um ambiente saudável para todos.",
        inline=False
    )
    
    embed.set_footer(text="Aproveite sua estadia!")
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    
    await member.send(embed=embed)

@bot.event
async def on_message(message):
    # Ignora mensagens de bots
    if message.author.bot:
        return
    
    # Verifica se é no servidor correto
    if message.guild is None or message.guild.id != GUILD_ID:
        return
    
    user_id = str(message.author.id)
    
    # Verifica se já está verificado
    cursor.execute("SELECT * FROM verified_users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        await bot.process_commands(message)
        return
    
    # Verifica se o usuário tem código pendente
    cursor.execute("SELECT codigo, expires_at FROM pending_codes WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result:
        codigo_correto, expira_em = result
        
        # Verifica se o código expirou
        if time.time() > expira_em:
            cursor.execute("DELETE FROM pending_codes WHERE user_id = ?", (user_id,))
            conn.commit()
            await message.delete()
            embed = discord.Embed(
                title="Código Expirado",
                description=f"**{message.author.display_name}**, seu código de verificação expirou.\n\nClique no botão **Iniciar Verificação** para gerar um novo código.",
                color=0xDC2626
            )
            await message.channel.send(embed=embed, delete_after=15)
            await bot.process_commands(message)
            return
        
        # Verifica se o código digitado está correto
        if message.content.strip() == codigo_correto:
            # Apaga a mensagem do usuário
            await message.delete()
            
            # Remove o código pendente
            cursor.execute("DELETE FROM pending_codes WHERE user_id = ?", (user_id,))
            
            # Adiciona o cargo
            role = message.guild.get_role(VERIFY_ROLE_ID)
            if role:
                await message.author.add_roles(role)
                
                # Salva no banco de verificados
                cursor.execute("INSERT INTO verified_users (user_id, username, verified_at) VALUES (?, ?, ?)",
                              (user_id, message.author.name, time.time()))
                conn.commit()
                
                # Envia mensagem de sucesso no chat (apaga rapidamente)
                success_embed = discord.Embed(
                    title="Verificação Concluída",
                    description=f"**{message.author.display_name}**, sua conta foi verificada com sucesso!",
                    color=0x10B981
                )
                msg = await message.channel.send(embed=success_embed)
                await asyncio.sleep(5)
                await msg.delete()
                
                # Envia mensagem de boas-vindas na DM
                try:
                    await send_welcome_message(message.author, message.guild)
                except discord.Forbidden:
                    # Se não conseguir enviar DM, avisa no chat
                    dm_error = discord.Embed(
                        title="Aviso",
                        description=f"**{message.author.display_name}**, não foi possível enviar mensagem de boas-vindas na sua DM. Verifique se suas mensagens diretas estão habilitadas.",
                        color=0xDC2626
                    )
                    await message.channel.send(embed=dm_error, delete_after=10)
            else:
                embed = discord.Embed(
                    title="Erro Interno",
                    description="Cargo de verificação não encontrado. Contate um administrador.",
                    color=0xDC2626
                )
                await message.author.send(embed=embed)
        else:
            # Código errado - apaga a mensagem e avisa
            await message.delete()
            embed = discord.Embed(
                title="Código Inválido",
                description=f"**{message.author.display_name}**, o código fornecido está incorreto.\n\nDigite o código correto ou clique no botão **Iniciar Verificação** para gerar um novo código.",
                color=0xDC2626
            )
            await message.channel.send(embed=embed, delete_after=10)
    
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"Bot conectado: {bot.user.name}")
    print(f"Servidor: {GUILD_ID}")
    print("Bot pronto para uso!")

@bot.command(name="verificar")
@commands.has_permissions(administrator=True)
async def send_verification(ctx):
    """Envia a mensagem de verificação (apenas administradores)"""
    
    if ctx.guild.id != GUILD_ID:
        await ctx.send("Comando não disponível neste servidor.", delete_after=5)
        return
    
    embed = discord.Embed(
        title="Verificação de Segurança",
        description="Para acessar os canais do servidor, é necessário concluir o processo de verificação.",
        color=0xDC2626
    )
    
    embed.add_field(
        name="Procedimento",
        value="1. Clique no botão **Iniciar Verificação**\n"
              "2. Um código será gerado exclusivamente para você\n"
              "3. Digite o código neste canal de texto\n"
              "4. Aguarde a confirmação automática\n\n"
              "O código é pessoal e será verificado automaticamente pelo sistema.",
        inline=False
    )
    
    embed.add_field(
        name="Por que verificar?",
        value="A verificação garante a segurança do servidor, prevenindo invasões e garantindo que apenas membros legítimos tenham acesso aos canais.",
        inline=False
    )
    
    embed.add_field(
        name="Importante",
        value="• O código expira em 3 minutos\n"
              "• Sua mensagem com o código será apagada automaticamente\n"
              "• Você receberá uma mensagem de boas-vindas na DM após verificado",
        inline=False
    )
    
    embed.set_footer(text="Sistema de Verificação • Segurança em primeiro lugar")
    
    view = View()
    view.add_item(VerifyButton())
    
    await ctx.send(embed=embed, view=view)
    await ctx.send("Mensagem de verificação enviada!", delete_after=3)

@bot.command(name="verificados")
@commands.has_permissions(administrator=True)
async def list_verified(ctx):
    """Lista os membros verificados"""
    cursor.execute("SELECT username, verified_at FROM verified_users ORDER BY verified_at DESC")
    users = cursor.fetchall()
    
    if not users:
        await ctx.send("Nenhum membro verificou a conta até o momento.")
        return
    
    import datetime
    lista = []
    for u in users[:20]:
        data = datetime.datetime.fromtimestamp(u[1]).strftime("%d/%m/%Y %H:%M")
        lista.append(f"• {u[0]} - {data}")
    
    embed = discord.Embed(
        title="Membros Verificados",
        description=f"Total: **{len(users)}** membros\n\n" + "\n".join(lista),
        color=0x10B981
    )
    await ctx.send(embed=embed)

@bot.command(name="remover")
@commands.has_permissions(administrator=True)
async def remove_verification(ctx, member: discord.Member):
    """Remove a verificação de um membro"""
    role = ctx.guild.get_role(VERIFY_ROLE_ID)
    
    if role in member.roles:
        await member.remove_roles(role)
        cursor.execute("DELETE FROM verified_users WHERE user_id = ?", (str(member.id),))
        conn.commit()
        
        embed = discord.Embed(
            title="Verificação Removida",
            description=f"A verificação de {member.mention} foi removida.",
            color=0xDC2626
        )
        await ctx.send(embed=embed)
        
        # Tenta avisar o membro
        try:
            embed_dm = discord.Embed(
                title="Verificação Removida",
                description=f"Sua verificação no servidor **{ctx.guild.name}** foi removida por um administrador.\n\nCaso tenha dúvidas, contate a administração.",
                color=0xDC2626
            )
            await member.send(embed=embed_dm)
        except:
            pass
    else:
        await ctx.send(f"{member.mention} não possui verificação ativa.")

@bot.command(name="limpar_pendentes")
@commands.has_permissions(administrator=True)
async def clear_pending(ctx):
    """Limpa todos os códigos pendentes"""
    cursor.execute("DELETE FROM pending_codes")
    conn.commit()
    await ctx.send("Todos os códigos pendentes foram removidos.")

@bot.command(name="resetar_verificacoes")
@commands.has_permissions(administrator=True)
async def reset_all_verifications(ctx):
    """Reseta todas as verificações (cuidado!)"""
    await ctx.send("⚠️ **ATENÇÃO!** Isso irá remover a verificação de TODOS os membros.\nDigite `CONFIRMAR` para prosseguir.")
    
    def check(m):
        return m.author == ctx.author and m.content == "CONFIRMAR"
    
    try:
        await bot.wait_for('message', timeout=30.0, check=check)
        
        role = ctx.guild.get_role(VERIFY_ROLE_ID)
        count = 0
        
        for member in ctx.guild.members:
            if role in member.roles:
                await member.remove_roles(role)
                count += 1
        
        cursor.execute("DELETE FROM verified_users")
        cursor.execute("DELETE FROM pending_codes")
        conn.commit()
        
        embed = discord.Embed(
            title="Reset Concluído",
            description=f"**{count}** membros tiveram suas verificações removidas.\n\nUma nova verificação será necessária para todos.",
            color=0xDC2626
        )
        await ctx.send(embed=embed)
        
    except asyncio.TimeoutError:
        await ctx.send("Comando cancelado. Tempo esgotado.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Você precisa ser administrador para usar este comando.", delete_after=5)

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)