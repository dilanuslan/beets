from __future__ import division  #it will change the / operator to mean true division throughout the module
from beets import plugins #enables to use the plugins that already exists
from beets import ui #command operations are defined under this library
from beets import util #utilization library
from beets import config #to be able to edit the configuration file of the application
from beets.plugins import BeetsPlugin #importing beets plugin packet to be able to write a new plugin

import os #operating system support
import re #regular expressions 

import requests #this library allows to make requests like get, post, etc. 

from contextlib import closing #returns a context manager that closes a page upon completion of the block
from tempfile import NamedTemporaryFile #the file is guaranteed to have a visible name in the file system

from mediafile import image_mime_type #this library belongs to beets and it is installed by pip, used for declaring the MIME type
from beets.util.artresizer import ArtResizer #artresizer also belongs to beets and it is used as a helper for this project

from beets.util import bytestring_path #this is used for setting the file paths  

from bs4 import BeautifulSoup #BeautifulSoup will be used for fetching lyrics

import warnings #for warning control
import html #This module defines functions to manipulate HTML.
import json #JavaScript Object Notation 
from unidecode import unidecode #takes Unicode data and tries to represent it in ASCII characters


class Image(object):

    def __init__(self, log, path=None, url=None, match=None, size=None): #constructor for candidate image
        self._log = log #for beetlogs.txt
        self.path = path #path of the image
        self.url = url #url of the image
        self.match = match #result of checking 
        self.size = size #size of the image

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


    req = requests.Request('GET', *args, **request_kwargs) #We require data from the web, so 'GET' is our main request method. 

    #This part was inspired from https://2.python-requests.org/en/v2.8.1/user/advanced/ in order to have an efficient use of requests library.
    #Basically, the template for the request is created

    #https://requests.readthedocs.io/en/master/_modules/requests/sessions/ used for understanding the functions
    with requests.Session() as s:
        s.headers = {'User-Agent': 'beets'}
        prepared = s.prepare_request(req)
        settings = s.merge_environment_settings(prepared.url, {}, None, None, None) #The function checks the environment and merge it with some settings.
        send_kwargs.update(settings)
        return s.send(prepared, **send_kwargs)


##### COVER ART SOURCE 

#this is an initial class for further definitions and logging
class CoverArtSource(object):

    def __init__(self, log, config, match_by=None): #constructor
        self._log = log
        self._config = config
        self.match_by = match_by  

    def _candidate(self, **kwargs):
        return Image(log=self._log, **kwargs) 

    def request(self, *args, **kwargs):
        return getLog(self._log, *args, **kwargs)


#The knowledge from this website is basically used in this part of the code: https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types

class ArtSource(CoverArtSource):
    placement = 'remote'  

    def get_image(self, candidate, plugin): #Downloads an image from an URL and checks whether it is an image or not. If so, returns a path to the downloaded image. Otherwise, returns None.
      
        if (plugin.maxwidth):
            candidate.url = ArtResizer.shared.proxy_url(plugin.maxwidth, candidate.url) #Modifies an image URL according the method, returning a new URL. For WEBPROXY, a URL on the proxy server is returned. Otherwise, the URL is returned unmodified.
        try:
            with closing(self.request(candidate.url, stream=True)) as resp:
                content_type = resp.headers.get('Content-Type', None) #content type should be either jpg or png

                #Download the image to a temporary file. 
                data = resp.iter_content(chunk_size=1024) #Iterates over the response data. When stream=True is set on the request, this avoids reading the content at once into memory for large responses. The chunk size is the number of bytes it should read into memory. This is not necessarily the length of each item returned as decoding can take place. 
                header = b'' 
                for chunk in data:
                    header += chunk
                    if (len(header) >= 32): #we can read up to 32 bytes
                        break
                else: #server could not return any data
                    return


                #function definition of image_mime_type will be given in the final report

                realcontenttype = image_mime_type(header) # This checks for a jpeg file with only the magic bytes (unrecognized by imghdr.what). imghdr.what returns none for that type of file, so_wider_test_jpeg is run in that case. It still returns None if it didn't match such a jpeg file.
                if (realcontenttype is None): #if image_mime_type return None, content type is assigned to realcontenttype
                    realcontenttype = content_type

                if (realcontenttype not in IMAGE_TYPES): #if the content type is not jpg or png, it is logged
                    self._log.debug('not a supported image: {}', realcontenttype or 'unknown content type')
                    return

                extension = b'.' + IMAGE_TYPES[realcontenttype][0] #extension will be either .jpg or .png

                if (realcontenttype != content_type): 
                    self._log.warning('Server specified {}, but returned a {} image. Correcting the extension to {}', content_type, realcontenttype, extension)

                with NamedTemporaryFile(suffix=extension, delete=False) as file:
                    file.write(header)  #write the first already loaded part of the image
                    for chunk in data:  #download the remaining part of the image
                        file.write(chunk)
                self._log.debug('downloaded art to: {0}', util.displayable_path(file.name)) #logging the download operation
                candidate.path = util.bytestring_path(file.name) #path of the candidate image is assigned using the bytestring_path function
                return

        except (IOError, requests.RequestException, TypeError) as exception: #if there is an error with downloading the image this code block will run
            self._log.debug('error downloading image: {}', exception)
            return


class CoverArtArchive(ArtSource): #this is the main website used in the project to get images 
    MATCHING_CRITERIA = ['release'] 

    if (util.SNI_SUPPORTED): #server name indication
        URL = 'https://coverartarchive.org/release/{mbid}/front' #mbid = MusicBrainz ID
    else:
        URL = 'http://coverartarchive.org/release/{mbid}/front'

    def get(self, album, plugin, paths): 
        if ('release' in self.match_by and album.mb_albumid): #Return the Cover Art Archive URLs using album MusicBrainz release ID.
            yield self._candidate(url=self.URL.format(mbid=album.mb_albumid))



SOURCE = ['coverart'] #album covers are taken from coverartarchive.org

ART_SOURCE = {
    'coverart': CoverArtArchive  
}
SOURCE_NAME = {a: b for b, a in ART_SOURCE.items()}

IMAGE_TYPES = { #the retrieved images should be in these formats
    'image/jpeg': [b'jpg', b'jpeg'], #b indicates byte literals
    'image/png': [b'png']
}
IMAGE_EXTENSIONS = [img for imgs in IMAGE_TYPES.values() for img in imgs]


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

    base_url = "https://api.genius.com" #our base url is the api for genius

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
            hit_artist = hit["result"]["primary_artist"]["name"]

            if (slugify(hit_artist) == slugify(artist)): #if slugified artist names are equal we scrape lyrics
                return self.scrapelyrics(self.get_url(hit["result"]["url"])) 

        self._log.debug('No matching artist \'{0}\'', artist)

    def search(self, artist, title):

        search_url = self.base_url + "/search" #obtained: https://api.genius.com/search
        data = {'q': title + " " + artist.lower()} #data is our query statement
        try:
            response = requests.get(search_url, data=data, headers=self.headers) #we try to get a response from this query (with artist name, title and specified headers)
        except requests.RequestException as exception: #if we can not get a response
            self._log.debug('Genius API request failed: {0}', exception)
            return None

        try: #try if we can return a valid json format
            return response.json() 
        except ValueError: #raise a value error if the response is not appropriate
            return None

    def scrapelyrics(self, html):

        soup = BeautifulSoup(html, "html.parser") #https://www.crummy.com/software/BeautifulSoup/bs4/doc/ soup holds the content of the desired page.

        [h.extract() for h in soup('script')] #Removing script tags from the html

        lyrics_div = soup.find("div", class_="lyrics") #find the div with the lyrics class
        if (not lyrics_div): #if can not be found
            self._log.debug('Unusual song page') 
            div2 = soup.find("div", class_=re.compile("Lyrics__Container")) #Compile a regular expression pattern into a regular expression object
            if (not div2): #if can not be found
                if (soup.find("div", class_=re.compile("LyricsPlaceholder__Message"), string="This song is an instrumental")): #if a placeholder statement is found
                    self._log.debug('Detected instrumental') #instrumental song 
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
    if (isinstance(text, bytes)): #check if text contains bytes
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

        self.art_candidates = {}  #Holds candidates corresponding to downloaded images between fetching them and placing them in the filesystem.

        self.maxwidth = self.config['maxwidth'].get(int) #it can be up to 2000 as defined in config.yaml

        cover_names = self.config['cover_names'].as_str_seq() #one of these elements in this list: ['cover', 'front', 'art', 'album', 'folder']
        self.cover_names = list(map(util.bytestring_path, cover_names)) #bytestring_path: Given a path, which is either a bytes or a unicode, returns a str path (ensuring that we never deal with Unicode pathnames).
        self.cautious = self.config['cautious'].get(bool) #gets False from the config file
        self.store_source = self.config['store_source'].get(bool) #gets False from the config file

        self.src_removed = (config['import']['move'].get(bool)) #gets yes from the config file

        if (self.config['auto']): #importing our plugin
            self.import_stages = [self.graduatorPlug]

        available_source = list(SOURCE) #putting our source into a list
        
        available_source = [(s, c) for s in available_source for c in ART_SOURCE[s].MATCHING_CRITERIA] #creating a list as [(CoverArtArchive, release)]
        source = plugins.sanitize_pairs(self.config['source'].as_pairs(default_value='*'), available_source) 
 
        self.source = [ART_SOURCE[s](self._log, self.config, match_by=[c]) for s, c in source]


        available_sources = list(self.LYRIC)
        sources = plugins.sanitize_choices(self.config['lyric'].as_str_seq(), available_sources)
        self.backends = [self.SOURCE_LYRICS[i](self.config, self._log) for i in sources]

        self.config['genius_api_key'].redact = True

       
    def graduatorPlug(self, task):
        if (task.is_album): 
            if (task.album.artpath and os.path.isfile(task.album.artpath)): #Album already has art (probably a re-import); skip it.
                return

            candidate = self.albumcover(task.album, task.paths)

            if (candidate):
                self.art_candidates[task] = candidate

    def setArt(self, album, candidate, delete=False):
        album.set_art(candidate.path, delete) #this is a built-in function from beets 
        album.store() #storing the changes in the database 

    def commands(self): #this function adds graduatorPlug to beets command list
        command = ui.Subcommand('graduatorPlug', help='help Dilan to graduate from ITU CE') # :)
        command.parser.add_option( #adding printing and forcing options to our plugin
            '-f', '--force', dest='force',  
            action='store_true', default=False,
            help='re-download art and lyrics when they already exist'
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
            self.finalize(lib, lib.albums(ui.decargs(args)), opts.force) 
        
            items = lib.items(ui.decargs(args)) #from database we reach out to items table
            for item in items: #for each item in items table
                self.getlyrics(lib, item, self.config['force']) #call getlyrics function with force = False
                if (item.lyrics): #if the lyrics are found
                    if (opts.printlyrics): #if there is a -p or --print option
                        ui.print_(item.lyrics) #print lyrics to console
                        ui.print_("\n") #print a space character after each song
                    if (opts.writetofile): #if there is a -w or --write option
                        self.writetofile(lib, item) #writing lyrics to file

            

        command.func = func #assign our functionalities
        return [command] #our command is working now

    def albumcover(self, album, paths):  #Given an Album object, returns a path to downloaded art for the album (or None if no art is found).  
        result = None

        for source in self.source:
            
                self._log.debug('trying source {0} for album {1.albumartist} - {1.album}', SOURCE_NAME[type(source)], album)
                # URLs might be invalid at this point, or the image may not fulfill the requirements
                for candidate in source.get(album, self, paths):
                    source.get_image(candidate, self)
                    result = candidate
                    self._log.debug(u'using {0.placement} image {1}'.format(source, util.displayable_path(result.path)))
                    break

                if (result):
                    break

        return result

    def finalize(self, lib, albums, force): #Get album cover for each of the albums. This implements the graduatorPlug CLI command.
        
        for album in albums:
            if (album.artpath and not force and os.path.isfile(album.artpath)):
                    message = ui.colorize('text_highlight_minor', 'has album art')
                    self._log.info('{0}: {1}', album, message)  #prints out to command line 
            else:
                if(force):
                    localpath = None
                else:
                    localpath = [album.path]

                candidate = self.albumcover(album, localpath)
                if (candidate): #if the album art is found
                    self.setArt(album, candidate)
                    message = ui.colorize('text_success', 'found album art') #print in green
                else:
                    message = ui.colorize('text_error', 'no art found') #print in red
                self._log.info('{0}: {1}', album, message) #prints out to command line

   

    def getlyrics(self, lib, item, force): #get lyrics from web and store them in the database

        if (not force and item.lyrics): #if not forced and lyrics already exists
            self._log.info('lyrics already exist: {0}', item)
            return
        
        lyrics = self.backends[0].fetch(item.artist, item.title) #call fetch function defined in Genius class

        if (lyrics): #if we find the lyrics
            self._log.info('fetched lyrics: {0}', item) #print to console the artist, title, and album title
            lyrics = clarify(lyrics, True) #this function clarifies the HTML content 
        else: #if lyrics not found
            self._log.info('lyrics not found: {0}', item)
            default_lyrics = self.config['default_lyrics'].get() #default_lyrics value is defined as None
            lyrics = default_lyrics
           
        item.lyrics = lyrics.strip() #assign lyrics to item's lyrics deleting whitespaces at the beginning and at the end of the text
        item.store() #store item in the database

    def writetofile(self, lib, item):

        save_path = '/Users/dilanuslan/Desktop/NewMusic/'  #the constant part of the path
        save_path = save_path + item.albumartist + '/' + item.album #the artist name and the album name is added to the path 
        filename = item.title + ".txt"  #the name of the file will be the song name

        finalname = os.path.join(save_path, filename) #adding filename to the path

        lyricsfile = open(finalname, "w") #creating the file for writing
        writetofile = item.lyrics #lyrics of the song is assigned to writetofile directly from the database
        lyricsfile.write(writetofile) #writing lyrics to the file

        lyricsfile.close() #closing the file
