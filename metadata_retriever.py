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

from coverart import *
from getlyrics import *


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


class metadata_retriever(BeetsPlugin): #derived from BeetsPlugin and RequestLogger

    LYRIC = ['genius'] #name of our source
    SOURCE_LYRICS = { #defining which class to call 
        'genius': Genius
    }
    
    def __init__(self): #constructor

        super(metadata_retriever, self).__init__()

        self.maxwidth = self.config['maxwidth'].get(int) #it can be up to 2000 as defined in config.yaml

        self.cover_name = self.config['cover_name'].as_str_seq() #bytestring_path: Given a path, which is either a bytes or a unicode, returns a str path (ensuring that we never deal with Unicode pathnames).

        if (self.config['auto']): #importing our plugin
            self.import_stages = [self.metadata_retriever]

        available_source = list(SOURCE) #putting our source into a list
        
        available_source = [(s, c) for s in available_source for c in ART_SOURCE[s].Type] #creating a list as [(CoverArtArchive, release)]
 
        self.source = [ART_SOURCE[s](self._log, self.config, match_by=[c]) for s, c in available_source]


        available_sources = list(self.LYRIC)

        self.backends = [self.SOURCE_LYRICS[i](self.config, self._log) for i in available_sources]

        self.config['genius_api_key'].redact = True


    def commands(self): #this function adds metadata_retriever to beets command list

        command = ui.Subcommand('metadata_retriever', help='fetch cover art and lyrics') # :)
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
                self.metadata_retriever(lib, lib.albums(ui.decargs(args))) 
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


    def metadata_retriever(self, lib, albums): #Get album cover for each of the albums. This implements the metadata_retriever CLI command.
        
        for album in albums:
            if (album.artpath and os.path.isfile(album.artpath)):
                message = ui.colorize('action', 'already has cover art')
                self._log.info('{0}: {1}', album, message)  #prints out to command line 
            else:
                localpath = [album.path]

                result = self.source[0].get(album, self, localpath)

                if(result):
                    image = True
                else:
                    image = None

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

        finalname = os.path.join(save_path, filename) #adding filename to the path

        if(os.path.exists(finalname)):
            return 
        else:

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
        if(os.path.exists(finalname2)):
            return 
        else:
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

