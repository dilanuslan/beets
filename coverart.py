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


class CoverArtArchive(): #this is the main website used in the project to get images 

    def __init__(self, log, config, match_by=None): #constructor
        self._log = log
        self._config = config
        self.match_by = match_by  

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
                    print("Image not found...")

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