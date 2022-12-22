#!/usr/bin/python

# v1.3.0

import urllib2
import tempfile
import os
import base64
import json
import re
import ssl
import math

from gimpfu import *

import string
#import Image
from array import array

UPSCALE = 4
INIT_FILE = "init.png"
GENERATED_FILE = "generated.png"
API_ENDPOINT = "api/generate"
API_VERSION = 5

HEADER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
HEADER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:105.0) Gecko/20100101 Firefox/105.0"

headers = {"Accept": HEADER_ACCEPT, "User-Agent": HEADER_USER_AGENT, "Content-Type": "application/json"}
ssl._create_default_https_context = ssl._create_unverified_context

initFile = r"{}".format(os.path.join(tempfile.gettempdir(), INIT_FILE))
generatedFile = r"{}".format(os.path.join(tempfile.gettempdir(), GENERATED_FILE))

def getImageData(image, drawable):
   pdb.file_png_save_defaults(image, drawable, initFile, initFile)
   initImage = open(initFile, "rb")
   encoded = base64.b64encode(initImage.read())
   return encoded

def displayGenerated(images):
   color = pdb.gimp_context_get_foreground()
   pdb.gimp_context_set_foreground((0, 0, 0))

   loadedImages = []
   for image in images:
      imageFile = open(generatedFile, "wb+")
      imageFile.write(base64.b64decode(image["image"]))
      imageFile.close()

      imageLoaded = pdb.file_png_load(generatedFile, generatedFile)
      loadedImages.append(imageLoaded)

      pdb.gimp_display_new(imageLoaded)
      # image, drawable, x, y, text, border, antialias, size, size_type, fontname
      pdb.gimp_text_fontname(imageLoaded, None, 2, 2, str(image["seed"]), -1, TRUE, 12, 1, "Sans")
      pdb.gimp_image_set_active_layer(imageLoaded, imageLoaded.layers[1])

   pdb.gimp_context_set_foreground(color)
   return loadedImages

def upscale_image(image, drawable, slice_size, promptStrength, steps, seed, prompt, url) :
   # pdb.gimp_image_undo_group_start(image)
   # pdb.gimp_context_push()
   width = image.width 
   height = image.height
   countX = int(math.ceil(float(width) / slice_size))
   countY = int(math.ceil(float(height) / slice_size))

   pdb.gimp_edit_copy(drawable)
   scaled_image = pdb.gimp_edit_paste_as_new()
   pdb.gimp_image_scale(scaled_image,countX*slice_size*UPSCALE,countY*slice_size*UPSCALE)
   pdb.gimp_layer_add_alpha(scaled_image.layers[0])
   pdb.gimp_drawable_edit_clear(scaled_image.layers[0])

   for y in range(countY):
      for x in range(countX):

         positionX = x*slice_size
         positionY = y*slice_size
         #copy slice
         pdb.gimp_image_select_rectangle(image, CHANNEL_OP_REPLACE, positionX, positionY, slice_size, slice_size)
         pdb.gimp_edit_copy(drawable)
         floating_slice_layer = pdb.gimp_edit_paste(image.layers[0], True)
         pdb.gimp_layer_resize(floating_slice_layer, slice_size, slice_size, 0, 0)

         #generate image
         generated_image = generate_images(image, floating_slice_layer, "MODE_UPSCALING", 0, promptStrength, steps, seed, 1, prompt, url)[0]
         #paste image into place
         pdb.gimp_image_select_rectangle(generated_image, CHANNEL_OP_REPLACE, 0, 0, slice_size*UPSCALE, slice_size*UPSCALE)
         pdb.gimp_edit_copy(generated_image.layers[1]) # seed text is at 0
         pdb.gimp_image_select_rectangle(scaled_image, CHANNEL_OP_REPLACE, positionX*UPSCALE, positionY*UPSCALE, slice_size*UPSCALE, slice_size*UPSCALE)
         floating_generated_layer = pdb.gimp_edit_paste(scaled_image.layers[0], True)
         
         pdb.gimp_floating_sel_anchor(floating_generated_layer)
         pdb.gimp_floating_sel_remove(floating_slice_layer)
         pdb.gimp_selection_none(image)
         pdb.gimp_selection_none(scaled_image)
         pdb.gimp_selection_none(generated_image)
   
   display = pdb.gimp_display_new(scaled_image)
      
   # pdb.gimp_context_pop()
   # pdb.gimp_image_undo_group_end(image)
   # pdb.gimp_displays_flush()
   #return

def generate_images(image, drawable, mode, initStrength, promptStrength, steps, seed, imageCount, prompt, url):
   # if image.width < 384 or image.width > 1024 or image.height < 384 or image.height > 1024:
      # raise Exception("Invalid image size. Image needs to be between 384x384 and 1024x1024.")

   pdb.gimp_progress_init("", None)
      
   data = {
      "mode": mode,
      "init_strength": float(initStrength),
      "prompt_strength": float(promptStrength),
      "steps": int(steps),
      "prompt": prompt,
      "image_count": int(imageCount),
      "api_version": API_VERSION
   }

   if drawable.width % 64 != 0:
      width = math.floor(drawable.width/64) * 64
   else:
      width = drawable.width

   if drawable.height % 64 != 0:
      height = math.floor(drawable.height/64) * 64
   else:
      height = drawable.height

   data.update({"width": int(width)})
   data.update({"height": int(height)})

   if mode == "MODE_IMG2IMG" or mode == "MODE_INPAINTING" or mode == "MODE_UPSCALING":
      imageData = getImageData(image, drawable)
      data.update({"init_img": imageData})

   seed = -1 if not seed else int(seed)
   data.update({"seed": seed})

   data = json.dumps(data)

   url = url + "/" if not re.match(".*/$", url) else url
   url = re.sub("http://", "https://", url)
   url = url + API_ENDPOINT

   request = urllib2.Request(url=url, data=data, headers=headers)
   pdb.gimp_progress_set_text("starting dreaming now...")

   try:
      response = urllib2.urlopen(request, timeout = 600)
      data = response.read()

      try:
         data = json.loads(data)
         return displayGenerated(data["images"])

      except Exception as ex:
         raise Exception(data)

   except Exception as ex:
      if isinstance(ex, urllib2.HTTPError):
         if ex.code == 405:
            raise Exception("GIMP plugin and stable-diffusion server don't match. Please update the GIMP plugin. If the error still occurs, please reopen the colab notebook.")
         if ex.code == 406:
            raise Exception("Unsupported mode on used checkpoint running on Colab notebook.")
      else:
         raise ex

   return []

def generate(image, drawable, mode, initStrength, promptStrength, steps, seed, imageCount, prompt, url):
   if prompt == "":
      raise Exception("Please enter a prompt.")

   if mode == "MODE_INPAINTING" and drawable.has_alpha == 0:
      raise Exception("Invalid image. For inpainting an alpha channel is needed.")

   if mode == "MODE_UPSCALING_128":
      upscale_image(image, drawable, 128, promptStrength, steps, seed, prompt, url)
   elif mode == "MODE_UPSCALING_256":
      upscale_image(image, drawable, 256, promptStrength, steps, seed, prompt, url)
   else: 
      generate_images(image, drawable, mode, initStrength, promptStrength, steps, seed, imageCount, prompt, url)

   if os.path.exists(initFile):
      os.remove(initFile)

   if os.path.exists(generatedFile):
      os.remove(generatedFile)

register(
   "stable-colab",
   "stable-colab",
   "stable-colab",
   "BlueTurtleAI",
   "BlueTurtleAI",
   "2022",
   "<Image>/AI/Stable Colab",
   "*",
   [
      (PF_RADIO, "mode", "Generation Mode", "MODE_TEXT2IMG", (
         ("Text -> Image", "MODE_TEXT2IMG"),
         ("Image -> Image", "MODE_IMG2IMG"),
         ("Inpainting", "MODE_INPAINTING"),
         ("Upscaling (128)", "MODE_UPSCALING_128"),
         ("Upscaling (256)", "MODE_UPSCALING_256")
      )),
      (PF_SLIDER, "initStrength", "Init Strength", 0.3, (0.0, 1.0, 0.1)),
      (PF_SLIDER, "promptStrength", "Prompt Strength", 7.5, (0, 20, 0.5)),
      (PF_SLIDER, "steps", "Steps", 50, (3, 500, 1)),
      (PF_STRING, "seed", "Seed (optional)", ""),
      (PF_SLIDER, "imageCount", "Number of images", 1, (1, 4,1)),
      (PF_STRING, "prompt", "Prompt", ""),
      (PF_STRING, "url", "Backend root URL", "")
   ],
   [],
   generate
)

main()