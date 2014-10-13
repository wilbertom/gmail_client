0.0.3

1. Renamed the library to gmail_client
2. Added documentation
3. Renamed `Message.unstar` to `Message.un_star`

0.0.4

1. Adding `Message` flags are "lazy"
2. A lot of `Message` methods return self to allow chaining
3. Adding & Removing `Message` flags/labels is "lazy"
4. `Message` Flags and Labels are sets instead of lists
5. A bunch of `Message` methods were turned into properties
6. Added `Message.add_flag` and `Message.remove_flag`
7. Added `Message.forced_fetch`
8. `Attachment.save` now returns the path where it was saved

