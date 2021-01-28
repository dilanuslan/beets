from __future__ import division  #it will change the / operator to mean true division throughout the module
from beets import plugins #enables to use the plugins that already exists
from beets import ui #command operations are defined under this library
from beets import util #utilization library
from beets import config #to be able to edit the configuration file of the application
from beets.plugins import BeetsPlugin #importing beets plugin packet to be able to write a new plugin

import os #operating system support
import re #regular expressions 

import requests #this library allows to make requests like get, post, etc. 
from bs4 import BeautifulSoup #BeautifulSoup will be used for fetching lyrics

import warnings #for warning control
import html #This module defines functions to manipulate HTML.
import json #JavaScript Object Notation 
from unidecode import unidecode #takes Unicode data and tries to represent it in ASCII characters

import musicbrainzngs #this library is used to reach Musicbrainz API directly to find all releases
from wordcloud import WordCloud #used for creating wordclouds of albums

import unittest


#args and kwargs are used to pass an argument list to a function
#With *args, any number of extra arguments can be tacked on to your current formal parameters
#**kwargs in function definitions in python is used to pass a keyworded, variable-length argument list. 

def getLog(log, *args, **kwargs): #defining the requests 
    
    request_kwargs = kwargs #kwargs as being a dictionary that maps each keyword to the value that we pass alongside it.
    send_kwargs = {}

    #stream = if False, the response content will be immediately downloaded
    #verify = if True, the SSL cert will be verified.
    #proxies = Dictionary mapping protocol to the URL of the proxy.
    #cert = if String, path to ssl client cert file (.pem). If Tuple, (‘cert’, ‘key’) pair.
    #timeout = How long to wait for the server to send data before giving up, as a float, or a (connect timeout, read timeout) tuple.

    for arg in ('stream', 'verify', 'proxies', 'cert', 'timeout'): #these are some of the parameters of a request
        if (arg in kwargs): #if our request has one of these, we add it to send_kwargs
            send_kwargs[arg] = request_kwargs.pop(arg)

    if 'message' in kwargs: #checking whether the special message is in kwargs or not
        message = kwargs.pop('message')
    else:
        message = 'getting URL' #default message 

    req = requests.Request('GET', *args, **request_kwargs) #We require data from the web, so 'GET' is our main request method. 

    #This part was inspired from https://2.python-requests.org/en/v2.8.1/user/advanced/ in order to have an efficient use of requests library.
    #Basically, we're creating the template for our request

    #https://requests.readthedocs.io/en/master/_modules/requests/sessions/ used for understanding the functions
    with requests.Session() as s:
        s.headers = {'User-Agent': 'beets'}
        prepared = s.prepare_request(req)
        settings = s.merge_environment_settings(prepared.url, {}, None, None, None) #The function checks the environment and merge it with some settings.
        send_kwargs.update(settings)
        log.debug('{}: {}', message, prepared.url)
        return s.send(prepared, **send_kwargs)


class CoverArtSource(object):

    def __init__(self, log, config, match_by=None): #constructor
        self._log = log
        self._config = config
        self.match_by = match_by  

    def request(self, *args, **kwargs):
        return getLog(self._log, *args, **kwargs)


#The knowledge from this website is basically used in this part of the code: https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types


class CoverArtArchive(CoverArtSource): #this is the main website used in the project to get images 

    Type = ['release'] 

    if (util.SNI_SUPPORTED): #server name indication
        URL = 'https://coverartarchive.org/release/{mbid}/front' #mbid = MusicBrainz ID
    else:
        URL = 'http://coverartarchive.org/release/{mbid}/front'

    def get(self, album, plugin, paths): 
        if (album.mb_albumid): #Return the Cover Art Archive URLs using album MusicBrainz release ID.
            save_path = '/Users/dilanuslan/Desktop/NewMusic/'  #the constant part of the path
            save_path = save_path + album.albumartist + '/' + album.album #the artist name and the album name is added to the path 
            filename = "cover.jpg"  

            finalname = os.path.join(save_path, filename) #adding filename to the path

            pic_url = self.URL.format(mbid=album.mb_albumid)

            with open(finalname, 'wb') as cover:
                response = requests.get(pic_url, stream=True)

                if not response.ok:
                    os.remove(finalname)

                for block in response.iter_content(1024):
                    if not block:
                        break

                    cover.write(block)

        return save_path


SOURCE = ['coverart'] #album covers are taken from coverartarchive.org

ART_SOURCE = {
    'coverart': CoverArtArchive  
}

IMAGE_TYPES = { #the retrieved images should be in these formats
    'image/jpeg': [b'jpg', b'jpeg'], #b indicates byte literals
    'image/png': [b'png']
}


class Lyric(object): #general class for lyrics

    def __init__(self, config, log):
        self._log = log

    def get_url(self, url): #https://www.w3schools.com/python/ref_requests_response.asp
        try:
            #https://docs.python.org/3/library/warnings.html
            with warnings.catch_warnings(): 
                warnings.simplefilter('ignore') #never print matching warnings
                req = requests.get(url, verify=False, headers={'User-Agent': 'USER_AGENT',}) 
        except requests.RequestException as exc:
            self._log.debug('request failed: {0}', exc)
            return

        #status_code returns a number that indicates the status (200 is OK, 404 is Not Found)
        #ok returns True if status_code is less than 400, otherwise False

        if (req.status_code == requests.codes.ok):
            return req.text #Returns the content of the response, in unicode
        else:
            self._log.debug('failed to fetch: {0} ({1})', url, req.status_code)

def slugify(text):
    #The unicode module exports a function that takes a string and returns a string that can be encoded to ASCII bytes in Python 3
    return re.sub(r'\W+', '-', unidecode(text).lower().strip()).strip('-') #we lower unicoded text and remove spaces at the beginning and end of the string, sub replaces \W+ characters in this text with -. Then we remove -'s.


class Genius(Lyric): #deriving genius class from lyric class

    url = "https://api.genius.com" #our base url is the api for genius

    def __init__(self, config, log):
        super(Genius, self).__init__(config, log)
        self.api_key = config['genius_api_key'].as_str() #get the api key from config file
        self.headers = { #this header implementation was taken from genius directly
            'Authorization': "Bearer %s" % self.api_key,
            'User-Agent': "USER_AGENT",
        }

    def fetch(self, artist, title): 

        #https://docs.python.org/3/library/json.html this document was really helpful for understanding json library in Python

        title = re.sub(r"[\(\[].*?[\)\]]", "", title) #removing these characters from the song title
        duet = artist.find("feat.") #find the index of feat.
        if(duet != -1): #if it exists in the artist name
            artist = artist[0:duet] #remove the feat and the rest of the artist
        
        json = self.search(artist, title) #Genius does not directly allow to scrape the api, first we try to get a matching url with artist name and title of the song
        #print(json) #used for debugging
        if (not json): #if search function returns None
            self._log.debug('Invalid JSON')
            return None

        for hit in json["response"]["hits"]: #assigning the artist name 
            artist_hit = hit["result"]["primary_artist"]["name"]

            if (slugify(artist_hit) == slugify(artist)): #if slugified artist names are equal we scrape lyrics
                return self.scrapelyrics(self.get_url(hit["result"]["url"])) 

        self._log.debug('No matching artist {0}', artist)


    def search(self, artist, title):

        search_url = self.url + "/search" #obtained: https://api.genius.com/search
        data = {'q': title + " " + artist.lower()} #data is our query statement
        response = requests.get(search_url, data=data, headers=self.headers) #we try to get a response from this query (with artist name, title and specified headers)

        return response.json() 


    def scrapelyrics(self, html):

        soup = BeautifulSoup(html, "html.parser") #https://www.crummy.com/software/BeautifulSoup/bs4/doc/ soup holds the content of the desired page.

        [h.extract() for h in soup('script')] #Removing script tags from the html

        lyrics_div = soup.find("div", class_="lyrics") #find the div with the lyrics class
        if (not lyrics_div): #if can not be found
            self._log.debug('Unusual song page') 
            div2 = soup.find("div", class_=re.compile("Lyrics__Container")) #Compile a regular expression pattern into a regular expression object
            if (not div2): #if can not be found
                if soup.find("div", class_=re.compile("LyricsPlaceholder__Message"), string="This song is an instrumental"): #if a placeholder statement is found
                    self._log.debug('Thid is an instrumental song') #instrumental song 
                    return "[Instrumental]" #this would be stored as the lyrics 
                else:
                    self._log.debug("Couldn't scrape the page..") #otherwise we can not scrape the page
                    return None


            #changing br elements with end of line character
            lyrics_div = div2.parent 
            for breaks in lyrics_div.find_all("br"):
                breaks.replace_with("\n")

            #finding ads and replacing them with end of line character
            ads = lyrics_div.find_all("div", class_=re.compile("InreadAd__Container"))

            for ad in ads:
                ad.replace_with("\n")

        return lyrics_div.get_text() #return the text we scraped from the webpage

def clarify(html, plain_text_out=False): #cleans the content of fetched html
   
    html = unescape(html) #call unescape function

    html = html.replace('\r', '\n')  #Normalize end of lines.
    html = re.sub(r' +', ' ', html)  #r is used for creating a raw string. Return the string obtained by replacing the leftmost non-overlapping occurrences of pattern in string by the replacement. Here whitespaces collapse.
    html = re.sub(r'(?s)<(script).*?</\1>', '', html)  #Stripping script tags.
    html = re.sub(u'\u2005', " ", html)  #replacing unicode with regular space

    return html


def unescape(text):
    if isinstance(text, bytes): #check if text contains bytes
        text = text.decode('utf-8', 'ignore') #decoding the text
    out = text.replace('&nbsp;', ' ') #replacing &nbsp with space character
    return out




                                                                        # PLUGIN #


class graduatorPlug(BeetsPlugin, CoverArtSource): #derived from BeetsPlugin and RequestLogger

    LYRIC = ['genius'] #name of our source
    SOURCE_LYRICS = { #defining which class to call 
        'genius': Genius
    }
    
    def __init__(self): #constructor

        super(graduatorPlug, self).__init__()

        self.maxwidth = self.config['maxwidth'].get(int) #it can be up to 2000 as defined in config.yaml

        self.cover_name = self.config['cover_name'].as_str_seq() #bytestring_path: Given a path, which is either a bytes or a unicode, returns a str path (ensuring that we never deal with Unicode pathnames).

        if (self.config['auto']): #importing our plugin
            self.import_stages = [self.graduatorPlug]

        available_source = list(SOURCE) #putting our source into a list
        
        available_source = [(s, c) for s in available_source for c in ART_SOURCE[s].Type] #creating a list as [(CoverArtArchive, release)]
 
        self.source = [ART_SOURCE[s](self._log, self.config, match_by=[c]) for s, c in available_source]


        available_sources = list(self.LYRIC)

        self.backends = [self.SOURCE_LYRICS[i](self.config, self._log) for i in available_sources]

        self.config['genius_api_key'].redact = True


    def commands(self): #this function adds graduatorPlug to beets command list

        command = ui.Subcommand('graduatorPlug', help='help Dilan to graduate from ITU CE') # :)
        command.parser.add_option( #finding cover arts
            '-c', '--cover', dest='coverart',
            action='store_true', default=False,
            help='find cover arts of albums',
        )
        command.parser.add_option( #finding lyrics
            '-l', '--lyric', dest='lyrics',
            action='store_true', default=False,
            help='find lyrics of the songs',
        )
        command.parser.add_option( #finding cover arts for all releases
            '-a', '--all', dest='allreleases',
            action='store_true', default=False,
            help='find cover arts for all releases',
        )
        command.parser.add_option( #printing lyrics of each song to command line
            '-p', '--print', dest='printlyrics',
            action='store_true', default=False,
            help='print lyrics to command line',
        )
        command.parser.add_option( #writing lyrics to file
            '-w', '--write', dest='writetofile',
            action='store_true', default=False,
            help='write lyrics to a text file',
        )

        def func(lib, opts, args): #main functionalities of the plugin

            print("\n")
            print("Please run the command with one of the following options: ")
            print("-c or --cover for finding the album cover")
            print("-l or --lyric for finding lyrics")
            print("-a or --all for finding the cover arts for all releases")
            print("-p or --print for printing lyrics to command line")
            print("-w or --write for writing lyrics to a file and creating a word cloud")
            print("\n\n")
         

            if(opts.coverart):
                self.graduatorPlug(lib, lib.albums(ui.decargs(args))) 
                print("\n")

            albums = lib.albums(ui.decargs(args)) #from database we reach out to items table
            for album in albums:
                if(opts.allreleases):
                    self.allreleases(lib, album)
                    print("\n")

            items = lib.items(ui.decargs(args)) #from database we reach out to items table

            for item in items: #for each item in items table

                if(opts.lyrics):
                    self.getlyrics(lib, item) #call getlyrics function 
                
                if (item.lyrics): #if the lyrics are found
                    if (opts.printlyrics): #if there is a -p or --print option
                        title = item.artist + " - " + item.title
                        title = ui.colorize('action', title)
                        ui.print_(title)
                        ui.print_(item.lyrics) #print lyrics to console
                        ui.print_("\n") #print a space character after each song
                    if (opts.writetofile): #if there is a -w or --write option
                        self.writetofile(lib, item) #writing lyrics to file
         

        command.func = func #assign our functionalities
        return [command] #our command is working now

    def albumcover(self, album, paths):  #Given an Album object, returns a path to downloaded art for the album (or None if no art is found).  
    
        result = None      
        # URLs might be invalid at this point, or the image may not fulfill the requirements
        result = self.source[0].get(album, self, paths)

        if (result):
            return result
        else:
            return None

    def graduatorPlug(self, lib, albums): #Get album cover for each of the albums. This implements the graduatorPlug CLI command.
        
        for album in albums:
            if (album.artpath and os.path.isfile(album.artpath)):
                message = ui.colorize('action', 'already has cover art')
                self._log.info('{0}: {1}', album, message)  #prints out to command line 
            else:
                localpath = [album.path]

                image = self.albumcover(album, localpath)
                if (image): #if the album art is found
                    album.store() #storing the changes in the database 
                    message = ui.colorize('text_success', 'found cover art') #print in green
                else:
                    message = ui.colorize('text_error', 'cover art not found') #print in red
                self._log.info('{0}: {1}', album, message) #prints out to command line
   

    def getlyrics(self, lib, item): #get lyrics from web and store them in the database

        if (item.lyrics): #if lyrics already exists
            message = ui.colorize('text_highlight', 'lyrics already exist')    
            self._log.info('{0}: {1}', message, item)  #prints out to command line 
            return
        
        lyrics = self.backends[0].fetch(item.artist, item.title) #call fetch function defined in Genius class

        if (lyrics): #if we find the lyrics
            message = ui.colorize('text_success', 'fetched lyrics')    
            self._log.info('{0}: {1}', message, item)  #prints out to command line 
            lyrics = clarify(lyrics, True) #this function clarifies the HTML content 
        else: #if lyrics not found
            message = ui.colorize('text_error', 'lyrics not found')    
            self._log.info('{0}: {1}', message, item)  #prints out to command line 
            default_lyrics = None #default_lyrics value is defined as None
            lyrics = default_lyrics
           
        item.lyrics = lyrics.strip() #assign lyrics to item's lyrics deleting whitespaces at the beginning and at the end of the text
        item.lyrics = re.sub(r"[\(\[].*?[\)\]]", "", item.lyrics)
        item.store() #store item in the database

    def writetofile(self, lib, item):

        save_path = '/Users/dilanuslan/Desktop/NewMusic/'  #the constant part of the path
        save_path = save_path + item.albumartist + '/' + item.album #the artist name and the album name is added to the path 
        filename = item.title + ".txt"  #the name of the file will be the song name

        message = "Writing {} to file.... Adding data into word cloud.....".format(item.title)
        print(message)

        finalname = os.path.join(save_path, filename) #adding filename to the path

        lyricsfile = open(finalname, "w") #creating the file for writing
        writetofile = item.lyrics #lyrics of the song is assigned to writetofile directly from the database
        lyricsfile.write(writetofile) #writing lyrics to the file

        lyricsfile.close() #closing the file

        #this part was inspired from: https://github.com/kvsingh/lyrics-sentiment-analysis/blob/master/wordclouds.py

        words = ''

        f = open(finalname, "rb")
        for s in f.readlines():
            sentence = s.decode('utf-8')
            #converted Turkish characters to English for a better visual
            sentence = re.sub('İ', 'I', sentence) 
            sentence = re.sub('Ş', 'S', sentence)
            sentence = re.sub('Ç', 'C', sentence)
            sentence = re.sub('Ö', 'O', sentence)
            words += sentence


        word_cloud = WordCloud(width=1000, height=500).generate(words.lower())

        save_path2 = '/Users/dilanuslan/Desktop/NewMusic/wordclouds/' 
        filename2 = item.albumartist + ".png"
        finalname2 = os.path.join(save_path2, filename2)  
        word_cloud.to_file(finalname2)
        image = word_cloud.to_image()

        f.close()


    def allreleases(self, lib, album):

        musicbrainzngs.set_useragent("beets.io", "0.1", "beets.io")
        URL = 'https://coverartarchive.org/release/'

        save_path = '/Users/dilanuslan/Desktop/NewMusic/'  #the constant part of the path
        save_path = save_path + album.albumartist + '/' + album.album #the artist name and the album name is added to the path 

        message = "Checking all releases for {0}".format(album.album)

        print (message)

        ##this block creates a list that contains the musicbrainz id's of all releases of an album 

        idlist = []

        release_group_dict = musicbrainzngs.get_release_group_by_id(album.mb_releasegroupid, includes=["releases"])

        base_key = 'release-count'

        for item in release_group_dict.values():
            release_keys = item.keys()
            if item[base_key] > 1 :
                key = 'release-list'
                if key in release_keys:
                    release_list_items = item[key]
                    for dic in release_list_items:
                        release_list_keys = dic.keys()
                        key2 = 'id'
                        if key2 in release_list_keys:
                            releaseid = dic[key2]
                            idlist.append(releaseid)


        ##this block makes a query for each id in the list, if the response turns ok the cover is downloaded to a file in the album's directory.

        for i in range(0, len(idlist)):
            filename = "cover{}.jpg".format(i+1)  

            finalname = os.path.join(save_path, filename) #adding filename to the path

            pic_url = "http://coverartarchive.org/release/{}/front".format(idlist[i])

            with open(finalname, 'wb') as cover:
                response = requests.get(pic_url, stream=True)

                if not response.ok:
                    os.remove(finalname)

                for block in response.iter_content(1024):
                    if not block:
                        break

                    cover.write(block)
