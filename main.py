import requests
from ghost_client import Ghost
import tempfile
import os
import json
import uuid
from mistune import Markdown, Renderer, InlineLexer
from urllib.parse import urlparse


CLIENT_ID = 'ghost-admin'
CLIENT_SECRET = '999999999999'  # see: https://api.ghost.org/docs/client-authentication for how to obtain
USERNAME = 'Admin_Username'
PASSWORD = 'Admin_Password'
BLOG_URL = 'https://myghostblog.com'


class ImageLinkUploader(InlineLexer):
    def __init__(self, download_folder, ghost, renderer, rules=None, **kwargs):
        super().__init__(renderer, rules, **kwargs)
        self.download_folder = download_folder
        self.ghost = ghost
        self.images_processed = []

    def _process_link(self, m, link, title=None):
        line = m.group(0)
        text = m.group(1)
        if line[0] == '!':
            # it is an image url! download it
            if link.startswith("http"):  # check to make sure the link is external (not already uploaded)
                # TODO-better way to check? urlparse?
                req = requests.get(link, allow_redirects=True)
                if req.status_code == 200:
                    print("Found image! - "+link)
                    fname = str(uuid.uuid4())+".jpg"  # TODO - filename based off of text (img desc)
                    path = os.path.join(self.download_folder, fname)
                    f = open(path, "wb")
                    f.write(req.content)
                    f.close()

                    # upload
                    if link == "https://i.imgur.com/mTatU0Y.jpg": #temp
                        relative_url = ghost.upload(file_path=path)
                        if (relative_url is not None) and len(relative_url) > 0:
                            # successful upload! add to images_processed
                            self.images_processed.append((text, link, relative_url))
                else:
                    print("failed to download image @ URL: "+link)


ghost = Ghost(
    BLOG_URL,
    client_id=CLIENT_ID, client_secret=CLIENT_SECRET
)

ghost.login(USERNAME, PASSWORD)

posts = ghost.posts.list(
    status='all',
    fields=('id', 'title', 'slug'),
    formats=('html', 'mobiledoc', 'plaintext'),
    limit='all'
)

# temporary upload folder
with tempfile.TemporaryDirectory() as tempdir:
    for post in posts: # loop through each post
        if post.mobiledoc is not None:
            mobiledoc = json.loads(post.mobiledoc)

            updated_mobiledoc = json.loads(post.mobiledoc)

            changes_made = 0
            if mobiledoc["cards"] is not None:
                for card_idx in range(len(mobiledoc["cards"])):
                    card = mobiledoc["cards"][card_idx]
                    if len(card) == 2:
                        if card[0] == "card-markdown":
                            if card[1]["markdown"] is not None:
                                # get the post markdown
                                post_markdown = card[1]["markdown"]

                                # pass markdown to ImageLinkUploader
                                # it will parse it, and upload linked images to the blog.
                                renderer = Renderer()
                                uploader = ImageLinkUploader(tempdir, ghost, renderer)
                                markdown = Markdown(renderer, inline=uploader)
                                markdown(post_markdown)

                                if len(uploader.images_processed) > 0:
                                    for img in uploader.images_processed:
                                        # change markdown to reference new relative image URL
                                        orig_img_md = "!["+img[0]+"]("+img[1]+")"
                                        new_img_md = "!["+img[0]+"]("+img[2]+")"
                                        print("change "+orig_img_md+" to "+new_img_md)
                                        new_post_markdown = post_markdown.replace(orig_img_md, new_img_md)

                                        changes_made += 1

                                    # update post markdown
                                    updated_mobiledoc["cards"][card_idx][1]["markdown"] = new_post_markdown

            if changes_made > 0:
                # make API request to update mobiledoc
                mobiledoc_json = json.dumps(updated_mobiledoc)
                ghost.posts.update(post.id, mobiledoc=mobiledoc_json)
                print("Updated %s links in post: "+post.title)
