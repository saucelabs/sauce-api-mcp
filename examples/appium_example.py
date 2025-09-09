from appium import webdriver
from appium.options.common import AppiumOptions
import os

# The Appium URL for the existing session (without credentials)
APPIUM_URL = "https://api.us-west-1.saucelabs.com/rdc/v2/sessions/e9921dbe-876e-48a1-9415-5a7b2b6dc16a/appium/wd/hub"

# Set Sauce Labs credentials in the options object
# It is recommended to set your Sauce Labs credentials as environment variables
options = AppiumOptions()
options.set_capability("appium:userName", os.environ.get("SAUCE_USERNAME"))
options.set_capability("appium:accessKey", os.environ.get("SAUCE_ACCESS_KEY"))

# Initialize the driver to connect to the existing session
driver = webdriver.Remote(command_executor=APPIUM_URL, options=options)

# Now you can interact with the device. For example, get the page source:
print(driver.page_source)

# Quitting the driver will end the session.
driver.quit()
