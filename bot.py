import os

import discord
import datetime
import random
import json
import sys
import asyncio
from io import StringIO
from io import BytesIO
from datetime import date
from dotenv import load_dotenv
from mcstatus import MinecraftServer

from discord.ext import tasks, commands


intents = discord.Intents().default()
intents.members = True #members is not a default part of intents

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DEBUG_MODE = os.getenv('DEBUG') != None
DEVELOPER_NAME = os.getenv('DEVELOPER_NAME')
NAP_SERVER_ID = int(os.getenv("NAP_SERVER_ID"))
NAP_DEV_OVERRIDE_ID = int(os.getenv("NAP_DEV_OVERRIDE_ID"))
DEVELOPER_ID = int(os.getenv("DEVELOPER_ID"))
bot = commands.Bot(command_prefix='!', intents=intents)


#stores settings per-server against the server id for that server
serverSettings = None

serverSettingsFileName = r"server_settings.json"
backupSettingsFileName = r"server_settings_backup.json"
rulesFileName = r"rules.txt"


def refreshSettingsFromFile():
    global serverSettings
    global serverSettingsFileName
    with open(serverSettingsFileName, "a+") as settingsFile:
        settingsFile.seek(0)
        file_string = settingsFile.read()
        if not file_string:
            serverSettings = {}
            settingsFile.write("{}") #basically make it an empty json file
            return
        else:
            settingsFile.seek(0)
            serverSettings = json.load(settingsFile)

def saveSettings():
    global serverSettings
    with open(serverSettingsFileName, "w+") as settingsFile:
        settingsFile.write(json.dumps(serverSettings))

def validateSettingsLoaded():
    global serverSettings
    global backupSettingsFileName
    if serverSettings == None:
        refreshSettingsFromFile()
        with open(backupSettingsFileName, "w+") as settingsBackupFile:
            settingsBackupFile.write(json.dumps(serverSettings))

def createSettingsForServer(guild):
    global serverSettings
    serverSettings[str(guild.id)] = { 
        "name" : guild.name,
    }
    saveSettings()

def validateSettingForServer(guild):
    global serverSettings
    validateSettingsLoaded()
    if not str(guild.id) in serverSettings:
        createSettingsForServer(guild)

def setServerSetting(guild, settingKey, settingValue):
    global serverSettings
    validateSettingsLoaded()
    if not str(guild.id) in serverSettings:
        createSettingsForServer(guild)
    serverSettings[str(guild.id)][settingKey] = settingValue
    saveSettings()

def getServerSetting(guild, settingKey):
    global serverSettings
    validateSettingsLoaded()
    validateSettingForServer(guild)
    if settingKey in serverSettings[str(guild.id)]:
        return serverSettings[str(guild.id)][settingKey]
    return None

auditLogFileName = r"audit.log"
auditLogLineWarning = 1
def addAuditLog(message):
    global auditLogFileName
    global auditLogLineWarning
    with open(auditLogFileName, "a+") as auditFile:
        auditFile.write(message + "\n")
        auditFile.close()

def getAuditLogLines():
    global auditLogFileName
    try:
        with open(auditLogFileName, "r") as auditFile:
            log = auditFile.read()
            auditFile.close()
            return log
    except FileNotFoundError:
        return ""


NAPAlliances = None
NAPListFileName = r"NAP.json"
NAPBackupListFileName = r"NAPBackup.json"
WelcomeMessageFileName = r"welcome_message.txt"

def refreshNAPFromFile():
    global NAPAlliances
    try:
        with open(NAPListFileName, "a+") as napFile:
            napFile.seek(0)
            file_string = napFile.read()
            if not file_string:
                NAPAlliances = {}
                napFile.write("{}") #basically make it an empty json file
                return
            else:
                napFile.seek(0)
                NAPAlliances = json.load(napFile)
    except FileNotFoundError:
        NAPAlliances = {}
        saveNAPFile()

def validateNAPAlliancesLoaded():
    global NAPAlliances
    if NAPAlliances == None:
        refreshNAPFromFile()
        with open(NAPBackupListFileName, "w+") as NAPBackupListFile:
            NAPBackupListFile.write(json.dumps(NAPAlliances))

def saveNAPFile():
    global NAPAlliances
    with open(NAPListFileName, "w+") as napFile:
        napFile.write(json.dumps(NAPAlliances))

def addNAPAlliance(tag, fullName):
    validateNAPAlliancesLoaded()
    newAlliance = {
        "tag" : tag,
        "name" : fullName
    }
    global NAPAlliances
    NAPAlliances[tag] = newAlliance
    saveNAPFile()

def removeNAPAlliance(tag):
    global NAPAlliances
    validateNAPAlliancesLoaded()
    if tag in NAPAlliances:
        return NAPAlliances.pop(tag, None)
    saveNAPFile()

def getNAPAllianceList():
    validateNAPAlliancesLoaded()
    global NAPAlliances
    return NAPAlliances

def setNAPAttribute(allianceTag, attribute, value):
    global NAPAlliances
    validateNAPAlliancesLoaded()
    if allianceTag in NAPAlliances:
        NAPAlliances[allianceTag][attribute] = value
        saveNAPFile()
        return True
    return False

def getNAPAllianceDetails(allianceTag):
    validateNAPAlliancesLoaded()
    global NAPAlliances
    if allianceTag in NAPAlliances:
        return NAPAlliances[allianceTag]
    return None


#untested
async def sendDevMessage(message):
    print("sending dev message")
    global DEVELOPER_ID
    devUser = bot.get_user(DEVELOPER_ID)
    if devUser != None:
        channel = await devUser.create_dm()
        await channel.send(message)
        

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

    print(f'{bot.user} is connected to the following guilds:')
    for guild in bot.guilds:
        print(f'    (id: {guild.id}) name: {guild.name}')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("No such command, use !help to list available commands")
    else:
        raise error

@bot.event
async def on_member_join(member):
    global NAP_SERVER_ID
    if member.guild.id == NAP_SERVER_ID:
        dm_channel = member.dm_channel
        if dm_channel == None:
            dm_channel = await member.create_dm()

        global WelcomeMessageFileName
        with open(WelcomeMessageFileName, "r") as welcomeMessageFile:
            welcomeMessageLines = welcomeMessageFile.read()
            await dm_channel.send(welcomeMessageLines)

async def announceToGuilds(message):
    global serverSettings

    validateSettingsLoaded()
    for guild in bot.guilds:
        validateSettingForServer(guild)

        #if this server has muted announcements, don't try and send anything!
        if getServerSetting(guild,"muteAnnouncements") == True:
            continue
        announceChannel = None
        channelName = getServerSetting(guild, "announceChannel")
        for channel in guild.text_channels:
            if channel.name == channelName:
                announceChannel = channel
                break
        
        if announceChannel != None:
            await announceChannel.send(message)
        else:
            await guild.text_channels[0].send("Warning! No announcement channel has been set for this server! Please set a channel with !setAnnouncementChannel, or mute announcements with !muteAnnouncements")        


async def validateContextIsAdmin(context, commandName):
    if context.author.guild_permissions.administrator:
        return True
    await context.channel.send(f"Only administrators can use the {commandName} command")
    return False


class ServerSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setAnnouncementChannel", help="Sets the channel that the bot will make announcements in your server to")
    async def setAnnounceChannel(self, context):
        if not await validateContextIsAdmin(context, "setAnnouncementChannel"):
            return
        desiredChannelName = context.message.content.replace("!setAnnouncementChannel ", "")
        foundChannel = False
        for channel in context.guild.text_channels:
            if channel.name == desiredChannelName:
                foundChannel = True
                setServerSetting(context.guild, "announceChannel", channel.name)
                await context.channel.send(f"Channel \"{desiredChannelName}\" has been added as this server's announcement channel. Please note if the name of this channel changes, you will need to reset this setting")
        if not foundChannel:
            await context.channel.send(f"Could not find channel {desiredChannelName}")

    @commands.command(name="muteAnnouncements", help="Mutes all announcements from this bot")
    async def muteAnnouncements(self, context):
        if not await validateContextIsAdmin(context, "muteAnnouncements"):
            return
        setServerSetting(context.guild, "muteAnnouncements", True)
        await context.channel.send("All announcements for this server have been muted, please use !unmuteAnnouncements to re-enable")

    @commands.command(name="unmuteAnnouncements", help="Unmutes announcements from this bot")
    async def unmuteAnnouncements(self, context):
        if not await validateContextIsAdmin(context, "unmuteAnnouncements"):
            return

        global serverSettings

        setServerSetting(context.guild, "muteAnnouncements", False)
        announceChannelName = getServerSetting(context.guild, "announceChannel")
        if announceChannelName == None:
            await context.channel.send("Announcements have been unmuted, but no announcement channel has been set! please set one with !setAnnouncementChannel")
        else:
            await context.channel.send(f"Announcements have been unmuted, the announcement channel for this server is {announceChannelName}")

async def validateNAPServer(context, commandName):
    global NAP_SERVER_ID
    global NAP_DEV_OVERRIDE_ID
    if not context.guild.id == NAP_SERVER_ID and not context.guild.id == NAP_DEV_OVERRIDE_ID:
        print(f"context id: {context.guild.id}  NAP id: {NAP_SERVER_ID}" )
        await context.channel.send(f"{commandName} can only be used on the NAP Top 50 server so that all other clans can see changes")
        return False
    return True

class NAP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="rules", help="pastes the NAP rules")
    async def getRules(self, context):
        with open(rulesFileName, "r") as rulesFile:
            rulesLines = rulesFile.read()
            asBytes = str.encode(rulesLines)
            await context.send("NAP Rules", file=discord.File(BytesIO(asBytes), "NAPRules.txt"))

    @commands.command(name="NAPList", help="prints out all clans in the NAP")
    async def getNAPList(self, context):
        allianceList = getNAPAllianceList()
        embedMessage = discord.Embed(title="NAP Alliance List")
        allianceArray = []
        for tag, alliance in allianceList.items():
            allianceArray.append(tag)

        sortFunc = lambda e : e.lower()

        allianceArray.sort(key=sortFunc)

        fullString = ""
        for tag in allianceArray:
            alliance = allianceList[tag]
            fullString += alliance["tag"] + " " + alliance["name"] + "\n"
        embedMessage.add_field(name="NAP Alliance List", value=fullString, inline=True)
        await context.send(embed=embedMessage)

    @commands.command(name="addAlliance", help="Adds a alliance to the NAP list, usage:  !addAlliance <alliance tag> <full alliance name>")
    async def addAlliance(self, context):
        if not await validateNAPServer(context, "addAlliance"):
            return
        tagAndName = context.message.content.replace("!addAlliance ", "")
        strings = tagAndName.split(" ")
        if len(strings) != 2:
            await context.channel.send(f"{tagAndName} is invalid usage of this command, please include the alliance tag and name separated by a single space e.g. !addAlliance [SCC] SomeCoolClan")
            return
        tag = strings[0]
        clanName = strings[1]
        
        addNAPAlliance(strings[0], strings[1])
        await context.channel.send(f"{tag} {clanName} has been added to the NAP list! Welcome to the NAP!")
        await announceToGuilds(f"{tag} {clanName} has just joined the NAP - (action by user {context.author.name})")
        
        addAuditLog(f"(Nick: {context.author.display_name} Name: {context.author.name}) added alliance {tag} {clanName} to NAP list")

    @commands.command(name="removeAlliance", help="Removes an alliance from the NAP list, usage:  !removeAlliance <alliance tag>")
    async def removeAlliance(self, context):
        if not await validateNAPServer(context, "removeAlliance"):
            return
        tag = context.message.content.replace("!removeAlliance ", "")
        details = removeNAPAlliance(tag)
        if details == None:
            await context.send(f"Alliance with tag {tag} does not exist")
        else:
            name = details["name"]
            message = f"Alliance {tag} {name} has been removed from the NAP list - (action by user {context.author.name}"
            await context.send(message)
            await announceToGuilds(message)
            addAuditLog(f"(Nick: {context.author.display_name} Name: {context.author.name}) removed alliance {tag} {name} from NAP list")

    @commands.command(name="setAllianceMarshal", help="Sets the name of the alliance's marshal, usage: !setAllianceMarshal <alliance tag> <marshal name>")
    async def setAllianceMarshal(self, context):
        if not await validateNAPServer(context, "setAllianceMarshal"):
            return
        contents = context.message.content.replace("!setAllianceMarshal ", "")
        contents = contents.split(" ")
        if len(contents) != 2:
            await context.send("Incorrect usage of !setAllianceMarshal, usage: !setAllianceMarshal <alliance tag> <marshal name>.\nDoes your marshal's name have a space in it? That is unsupported")
            return
        tag = contents[0]
        name = contents[1]
        success = setNAPAttribute(tag, "marshal", name)
        if not success:
            await context.send("Alliance is not registered in the NAP, please register with !addAlliance")
            return
        await context.send(f"{tag} Alliance marshal has been set to {name}")
        addAuditLog(f"(Nick: {context.author.display_name} Name: {context.author.name}) set alliance {tag} marshal name to {name}")


    @commands.command(name="setAllianceCoords", help="Sets the coordinates of the alliance, usage: !setAllianceCoords <alliance tag> <x,y>")
    async def setAllianceCoords(self, context):
        if not await validateNAPServer(context, "setAllianceCoords"):
            return
        contents = context.message.content.replace("!setAllianceCoords ", "")
        contents = contents.split(" ")
        if len(contents) != 2:
            await context.send("Incorrect usage of !setAllianceCoords, usage: !setAllianceMarshal <alliance tag> <x,y>.\n")
            return
        tag = contents[0]
        coords = contents[1]
        success = setNAPAttribute(tag, "coords", coords)
        if not success:
            await context.send("Alliance is not registered in the NAP, please register with !addAlliance")
            return
        await context.send(f"{tag} Alliance coordinates have been set to {coords}")
        addAuditLog(f"(Nick: {context.author.display_name} Name: {context.author.name}) set alliance {tag} coordinates to {coords}")


    @commands.command(name="setAllianceName", help="Sets the full name of the alliance, usage: !setAllianceCoords <alliance tag> <fullName>")
    async def setAllianceName(self, context):
        if not await validateNAPServer(context, "setAllianceName"):
            return
        contents = context.message.content.replace("!setAllianceName ", "")
        contents = contents.split(" ")
        if len(contents) != 2:
            await context.send("Incorrect usage of !setAllianceName, usage: !setAllianceMarshal <alliance tag> <name>.\nDoes your alliance have a space in the name? This is unsupported!")
            return
        tag = contents[0]
        name = contents[1]
        success = setNAPAttribute(tag, "name", name)
        if not success:
            await context.send("Alliance is not registered in the NAP, please register with !addAlliance")
            return
        await context.send(f"{tag} Alliance name has been set to {name}")
        addAuditLog(f"(Nick: {context.author.display_name} Name: {context.author.name}) set alliance {tag} name to {name}")

    @commands.command(name="allianceDetails", help="Gets all the registered details for the alliance, usage:  !getAllianceDetails <tag>")
    async def getAllianceDetails(self, context):
        tag = context.message.content.replace("!allianceDetails ", "")
        details = getNAPAllianceDetails(tag)
        if details == None:
            await context.send(f"alliance {tag} has not been registered, please register with !addAlliance")
            return
        
        details_string = tag + " " + details["name"]
        if "marshal" in details:
            details_string += "\nMarshal: " + details["marshal"]
        if "coords" in details:
            details_string += "\nCoordinates: " + details["coords"]
        await context.send(details_string)


    @commands.command(name="auditLog", help="Makes the bot send the NAP audit log as a txt file attachment")
    async def getAuditLog(self, context):
        if not await validateNAPServer(context, "getAuditLog"):
            return
        logLines = getAuditLogLines()
        asBytes = str.encode(logLines)
        #content = b"".join(asBytes)
        await context.send("Audit Log", file=discord.File(BytesIO(asBytes), "auditLog.txt"))


bot.add_cog(ServerSettings(bot))
bot.add_cog(NAP(bot))

bot.run(TOKEN)
