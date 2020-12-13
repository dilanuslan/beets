from __future__ import division  #it will change the / operator to mean true division throughout the module
from beets import plugins #enables to use the plugins that already exists
from beets import ui #subcommand is defined under this library
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

from beets.util import bytestring_path #this is used for setting the paths  

from bs4 import BeautifulSoup #BeautifulSoup will be used for fetching lyrics

class Candidate(object):
    
    CANDIDATE_BAD = 0 #not usable
    CANDIDATE_EXACT = 1 #usable
    MATCH_EXACT = 0 #exact match

    def __init__(self, log, path=None, url=None, source='', match=None, size=None): #constructor for candidate image
        self._log = log #for beetlogs.txt
        self.path = path #path of the image
        self.url = url #url of the image
        self.source = source #source of the image (website)
        self.check = None #checking whether the image is usable or not
        self.match = match #result of checking 
        self.size = size #size of the image

    #validations by the path and the size

    def _validate(self, plugin):

        if not self.path:
            return self.CANDIDATE_BAD

        if not self.size:
            return self.CANDIDATE_EXACT

    def validate(self, plugin):
        self.check = self._validate(plugin)
        return self.check


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
        if arg in kwargs: #if our request has one of these, we add it to send_kwargs
            send_kwargs[arg] = request_kwargs.pop(arg)

    if 'message' in kwargs: #checking whether the special message is in kwargs or not
        message = kwargs.pop('message')
    else:
        message = 'getting URL' #default message 

    req = requests.Request('GET', *args, **request_kwargs) #We require data from the web, so 'GET' is our main request method. 

    #This part was inspired from https://2.python-requests.org/en/v2.8.1/user/advanced/ in order to have an efficient use of requests library.
    #Basically, we're creating the template for our request
    with requests.Session() as s:
        s.headers = {'User-Agent': 'beets'}
        prepared = s.prepare_request(req)
        settings = s.merge_environment_settings(prepared.url, {}, None, None, None) #The function checks the environment and merge it with some settings.
        send_kwargs.update(settings)
        log.debug('{}: {}', message, prepared.url)
        return s.send(prepared, **send_kwargs)

class RequestLogger(object): #Adds a Requests wrapper to the class that uses the logger

    def request(self, *args, **kwargs):
        return getLog(self._log, *args, **kwargs)


##### COVER ART SOURCES 

#this is an initial class for further definitions and logging
class CoverArtSource(RequestLogger):
    MATCHING_CRITERIA = ['default']

    def __init__(self, log, config, match_by=None): #constructor
        self._log = log
        self._config = config
        self.match_by = match_by or self.MATCHING_CRITERIA #assign matching result or default definition

    def _candidate(self, **kwargs):
        return Candidate(source=self, log=self._log, **kwargs) 


#The knowledge from this website is basically used in this part of the code: https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types

class ArtSource(CoverArtSource):
    LOCAL_STR = 'remote'  #remote states that the source is not local 

    def get_image(self, candidate, plugin): #Downloads an image from an URL and checks whether it is an image or not. If so, returns a path to the downloaded image. Otherwise, returns None.
      
        if plugin.maxwidth:
            candidate.url = ArtResizer.shared.proxy_url(plugin.maxwidth, candidate.url) #Modifies an image URL according the method, returning a new URL. For WEBPROXY, a URL on the proxy server is returned. Otherwise, the URL is returned unmodified.
        try:
            with closing(self.request(candidate.url, stream=True, message=u'downloading image')) as resp:
                content_type = resp.headers.get('Content-Type', None) #content type should be either jpg or png

                #Download the image to a temporary file. 
                data = resp.iter_content(chunk_size=1024) #Iterates over the response data. When stream=True is set on the request, this avoids reading the content at once into memory for large responses. The chunk size is the number of bytes it should read into memory. This is not necessarily the length of each item returned as decoding can take place. 
                header = b'' #header will be a byte literal
                for chunk in data:
                    header += chunk
                    if len(header) >= 32: #we can read up to 32 bytes
                        break
                else: #server could not return any data
                    return


                #function definition of image_mime_type will be given in the final report

                realcontenttype = image_mime_type(header) # This checks for a jpeg file with only the magic bytes (unrecognized by imghdr.what). imghdr.what returns none for that type of file, so_wider_test_jpeg is run in that case. It still returns None if it didn't match such a jpeg file.
                if realcontenttype is None: #if image_mime_type return None, content type is assigned to realcontenttype
                    realcontenttype = content_type

                if realcontenttype not in IMAGE_TYPES: #if the content type is not jpg or png, it is logged
                    self._log.debug('not a supported image: {}', realcontenttype or 'unknown content type')
                    return

                extension = b'.' + IMAGE_TYPES[realcontenttype][0] #extension will be either .jpg or .png

                if realcontenttype != content_type: 
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
    NAME = "Cover Art Archive" #name of the website
    MATCHING_CRITERIA = ['release'] 

    if util.SNI_SUPPORTED: #server name indication
        URL = 'https://coverartarchive.org/release/{mbid}/front' #mbid = MusicBrainz ID
    else:
        URL = 'http://coverartarchive.org/release/{mbid}/front'

    def get(self, album, plugin, paths): ###############bu bir generator!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        if 'release' in self.match_by and album.mb_albumid: #Return the Cover Art Archive URLs using album MusicBrainz release ID.
            yield self._candidate(url=self.URL.format(mbid=album.mb_albumid), match=Candidate.MATCH_EXACT)

SOURCE = ['coverart'] 

ART_SOURCE = {
    'coverart': CoverArtArchive,  
}
SOURCE_NAME = {a: b for b, a in ART_SOURCE.items()}

IMAGE_TYPES = { #the retrieved images should be in these formats
    'image/jpeg': [b'jpg', b'jpeg'], #b indicates byte literals
    'image/png': [b'png']
}
IMAGE_EXTENSIONS = [img for imgs in IMAGE_TYPES.values() for img in imgs]


                                                                        # PLUGIN #


class graduatorPlug(BeetsPlugin, RequestLogger): #derived from BeetsPlugin and RequestLogger
    
    def __init__(self): #constructor
        super(graduatorPlug, self).__init__()

        self.art_candidates = {}  #Holds candidates corresponding to downloaded images between fetching them and placing them in the filesystem.

        self.maxwidth = self.config['maxwidth'].get(int) #it can be up to 2000 as defined in config.yaml

        cover_names = self.config['cover_names'].as_str_seq() #one of these elements in this list: ['cover', 'front', 'art', 'album', 'folder']
        self.cover_names = list(map(util.bytestring_path, cover_names)) #bytestring_path: Given a path, which is either a bytes or a unicode, returns a str path (ensuring that we never deal with Unicode pathnames).
        self.cautious = self.config['cautious'].get(bool) #gets False from the config file
        self.store_source = self.config['store_source'].get(bool) #gets False from the config file

        self.src_removed = (config['import']['move'].get(bool)) #gets yes from the config file

        if (self.config['auto']): #Enable two import hooks when fetching is enabled.
            self.import_stages = [self.graduatorPlug]

        available_source = list(SOURCE)
        
        available_source = [(s, c) for s in available_source for c in ART_SOURCE[s].MATCHING_CRITERIA]
        source = plugins.sanitize_pairs(self.config['source'].as_pairs(default_value='*'), available_source)

        self.source = [ART_SOURCE[s](self._log, self.config, match_by=[c]) for s, c in source]

    def graduatorPlug(self, session, task):
        if (task.is_album): 
            if (task.album.artpath and os.path.isfile(task.album.artpath)): #Album already has art (probably a re-import); skip it.
                return

            candidate = self.albumcover(task.album, task.paths)

            if (candidate):
                self.art_candidates[task] = candidate

    def _set_art(self, album, candidate, delete=False):
        album.set_art(candidate.path, delete)
        if self.store_source:
            # store the source of the chosen artwork in a flexible field
            self._log.debug("Storing art_source for {0.albumartist} - {0.album}", album)
            album.art_source = SOURCE_NAME[type(candidate.source)]
        album.store()

    def commands(self): #this function adds graduatorPlug to beets command list
        command = ui.Subcommand('graduatorPlug', help='help Dilan to graduate from ITU CE') # :)
        command.parser.add_option(
            '-f', '--force', dest='force',
            action='store_true', default=False,
            help=u're-download art when already present'
        )

        def func(lib, opts, args): #main functionalities of the plugin
            self.finalize(lib, lib.albums(ui.decargs(args)), opts.force)
            #self.getLyrics()

        command.func = func
        return [command]

    def albumcover(self, album, paths):  #Given an Album object, returns a path to downloaded art for the album (or None if no art is found).  
        result = None

        for source in self.source:
            
                self._log.debug('trying source {0} for album {1.albumartist} - {1.album}', SOURCE_NAME[type(source)], album)
                # URLs might be invalid at this point, or the image may not fulfill the requirements
                for candidate in source.get(album, self, paths):
                    source.get_image(candidate, self)
                    if candidate.validate(self):
                        result = candidate
                        self._log.debug(
                            u'using {0.LOCAL_STR} image {1}'.format(source, util.displayable_path(result.path)))
                        break
                if result:
                    break

        return result

    def finalize(self, lib, albums, force): #Get album cover for each of the albums. This implements the graduatorPlug CLI command.
        
        for album in albums:
            if (album.artpath and not force and os.path.isfile(album.artpath)):
                    message = ui.colorize('text_highlight_minor', 'has album art')
                    self._log.info('{0}: {1}', album, message)  #prints out to command line 
            else:
                localpath = None if force else [album.path]

                candidate = self.albumcover(album, localpath)
                if (candidate): #if the album art is found
                    self._set_art(album, candidate)
                    message = ui.colorize('text_success', 'found album art') #print in green
                else:
                    message = ui.colorize('text_error', 'no art found') #print in red
                self._log.info('{0}: {1}', album, message) #prints out to command line


