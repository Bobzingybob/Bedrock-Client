"""Base profile class for Bedrock launcher settings."""


class BaseProfile:
    """Base class for optimization profiles.
    
    Subclasses define:
    - name: display name
    - description: short description
    - options: dict of options.txt key-value pairs
    """
    
    name = "base"
    description = "Base profile"
    options = {}
    
    def get_options(self):
        """Return the options.txt settings for this profile."""
        return dict(self.options)
    
    def __repr__(self):
        return f"<Profile: {self.name}>"
