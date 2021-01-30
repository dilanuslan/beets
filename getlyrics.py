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

class Lyric(): #general class for lyrics

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
                    self._log.debug("Couldn't scrape the page...") #otherwise we can not scrape the page
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

def slugify(text):
    #The unicode module exports a function that takes a string and returns a string that can be encoded to ASCII bytes in Python 3
    return re.sub(r'\W+', '-', unidecode(text).lower().strip()).strip('-') #we lower unicoded text and remove spaces at the beginning and end of the string, sub replaces \W+ characters in this text with -. Then we remove -'s.

