from functools import partial
import numpy as np
import os
from PIL import Image
from pyparsing import CaselessLiteral, Optional
import re
import requests
import shutil
from slack.bot import register, SlackBot
from slack.command import HistoryCommand, MessageCommand, UploadCommand
from slack.parsing import symbols
from wordcloud import WordCloud, STOPWORDS, ImageColorGenerator
import tempfile


class WordcloudBot(SlackBot):
    def __init__(self, slack):
        self.name = 'Display a wordcloud'
        self.expr = (CaselessLiteral('wordcloud') +
                     Optional(symbols.flag_with_arg('user', symbols.user_name)) +
                     Optional(symbols.flag_with_arg('channel', symbols.channel_name)) +
                     Optional(symbols.flag('all_channels')) +
                     Optional(symbols.flag_with_arg('image', symbols.link)))

        self.doc = ('Make a wordcloud using chat history, with optional filters:\n'
                    '\twordcloud [--user <user>] [--channel <channel> | --all_channels] [--image <image>]')

    @register(name='name', expr='expr', doc='doc')
    async def command_wordcloud(self, user, in_channel, parsed):
        kwargs = {}
        if 'user' in parsed:
            kwargs['user'] = parsed['user']

        if 'all_channels' in parsed:
            pass
        elif 'channel' in parsed:
            kwargs['channel'] = parsed['channel']
        else:
            kwargs['channel'] = in_channel
        kwargs['callback'] = partial(self._history_handler,
                                     user,
                                     in_channel,
                                     parsed['image'][1:-1] if 'image' in parsed else None)
        return HistoryCommand(**kwargs)

    async def _history_handler(self, user, in_channel, image_url, hist_list):
        if not hist_list:
            return
        try:
            image_file = await WordcloudBot.get_image(image_url) if image_url else None
        except ValueError:
            return MessageCommand(channel='None', user=user, text='Image {} not found.'.format(image_url))

        text = (rec.text for rec in hist_list)
        # Leslie's regex for cleaning mentions, emoji and uploads
        text = (re.sub('<[^>]*>|:[^\s:]*:|uploaded a file:', '', t) for t in text)

        out_file = await WordcloudBot.make_wordcloud(' '.join(text), image_file)
        return UploadCommand(channel=in_channel, user=user, file_name=out_file, delete=True)

    @staticmethod
    async def make_wordcloud(text, image_file=None):
        kwargs = {}
        import random

        def make_random_word():
            l = random.randint(1, 3)
            return ''.join(chr(random.randint(ord('a'), ord('z'))) for _ in range(l))

        text += ' '.join(make_random_word() for _ in range(2000))
        if image_file:
            ttd_coloring = np.array(Image.open(image_file))
            kwargs['mask'] = ttd_coloring
            kwargs['color_func'] = ImageColorGenerator(ttd_coloring)

        # TODO: Turn some of the options into flags
        wc = WordCloud(background_color='white',
                       max_words=2000,
                       stopwords=STOPWORDS,
                       max_font_size=40,
                       random_state=42,
                       **kwargs)

        wc.generate(text)
        # TODO: Replace this with a tempfile
        name = next(tempfile._get_candidate_names()) + '.png'
        wc.to_file(name)

        if image_file:
            os.remove(image_file)
        return name

    @staticmethod
    async def get_image(url):
        r = requests.get(url, stream=True)
        if r.status_code == 200:
            out_name = next(tempfile._get_candidate_names()) + '.png'
            with open(out_name, 'wb') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)
            return out_name