import os
import sys
import django
from django.apps import apps
from django.db.models import Q
from datetime import date
from asgiref.sync import sync_to_async
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.types import DomainDict
from rasa_sdk.executor import CollectingDispatcher
from abc import ABC, abstractmethod

# Setting up Django environment
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Project.settings")
django.setup()

# Get models
Movie = apps.get_model('Movies', 'Movie')
Showtime = apps.get_model('Movies', 'Showtime')
CinemaHall = apps.get_model('Movies', 'CinemaHall')
Genre = apps.get_model('Movies', 'Genre')

# Error messages
MOVIE_NOT_FOUND = "I couldn't find information about {movie_name}."
GENERAL_ERROR = "Sorry, an error occurred: {error}"
PROVIDE_MOVIE_NAME = "Please provide the movie name."
NO_RESULTS_FOUND = "No {item_type} found."

# Helper functions
@sync_to_async
def get_movie_by_name(name: str) -> Movie:
    """Get a movie by its name using flexible matching."""
    if not name:
        return None
        
    try:
        # Clean the input name and try Arabic to English number conversion
        clean_name = name.strip().lower()
        arabic_to_english = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
        clean_name = clean_name.translate(arabic_to_english)
        
        # Try exact match first (case insensitive)
        movie = Movie.objects.filter(title__iexact=clean_name).first()
        if movie:
            return movie
            
        # Try exact match with common variations
        variations = [
            clean_name,
            clean_name.replace(':', ''),  # Remove colons
            clean_name.replace('-', ' '),  # Replace hyphens with spaces
            clean_name.replace('&', 'and'),  # Replace & with 'and'
            ' '.join(clean_name.split()),  # Normalize spaces
            clean_name.replace('2', 'two'),  # Replace numbers with words
            clean_name.replace('two', '2'),  # Replace words with numbers
            clean_name.replace('موانا', 'moana'),  # Common Arabic title translations
            clean_name.replace('الجزء', 'part'),
        ]
        
        for variation in variations:
            movie = Movie.objects.filter(title__iexact=variation).first()
            if movie:
                return movie

        # If no exact match, try partial matching with high threshold
        words = clean_name.split()
        if len(words) > 0:
            # Create a query that matches all words in any order
            query = Q()
            for word in words:
                if len(word) > 2:  # Ignore very short words
                    query &= Q(title__icontains=word)
            
            movies = Movie.objects.filter(query)
            if movies.exists():
                # If we have matches, find the closest one
                best_match = None
                highest_similarity = 0
                
                for movie in movies:
                    # Calculate word-based similarity
                    movie_words = set(movie.title.lower().split())
                    search_words = set(words)
                    common_words = movie_words.intersection(search_words)
                    
                    # Calculate similarity ratio
                    similarity = len(common_words) / max(len(movie_words), len(search_words))
                    
                    # Boost score for sequential word matches
                    if all(word in movie.title.lower() for word in words):
                        similarity += 0.3
                    
                    # Boost score for matching first word
                    if movie.title.lower().startswith(words[0]):
                        similarity += 0.2
                    
                    # Extra boost for number matches (e.g., "2" matches "2" or "two")
                    if any(w.isdigit() for w in words) and any(w.isdigit() for w in movie_words):
                        similarity += 0.2
                    
                    if similarity > highest_similarity:
                        highest_similarity = similarity
                        best_match = movie
                
                # Only return if we have a very good match (75% or better)
                if highest_similarity >= 0.75:
                    return best_match
        
        return None
    except Exception as e:
        print(f"Error in get_movie_by_name: {str(e)}")
        return None

@sync_to_async
def get_movie_showtimes(movie_id: int) -> List[Showtime]:
    """Get showtimes for a movie."""
    return list(Showtime.objects.filter(movie_id=movie_id).select_related('cinema_hall'))

@sync_to_async
def get_movie_seats(movie_id: int) -> int:
    """Get available seats for a movie."""
    return Movie.objects.get(id=movie_id).seats_available

@sync_to_async
def get_movie_price(movie_id):
    return Movie.objects.get(id=movie_id).ticket_price

@sync_to_async
def get_movie_cinema_halls(movie_id):
    try:
        showtimes = Showtime.objects.filter(movie_id=movie_id).select_related('cinema_hall')
        cinema_halls = set(showtime.cinema_hall.name for showtime in showtimes)
        return list(cinema_halls)
    except Exception:
        return []

@sync_to_async
def get_cinema_hall_by_name(name: str) -> CinemaHall:
    """Get a cinema hall by its name using flexible matching."""
    if not name:
        return None
    
    try:
        # Clean the input name
        clean_name = name.strip()
        
        # Try exact match first (case insensitive)
        cinema = CinemaHall.objects.filter(name__iexact=clean_name).first()
        if cinema:
            return cinema
            
        # Try partial match
        cinemas = CinemaHall.objects.filter(name__icontains=clean_name)
        if cinemas:
            return cinemas.first()
                
        return None
    except Exception as e:
        print(f"Error in get_cinema_hall_by_name: {str(e)}")
        return None

@sync_to_async
def get_cinema_hall_showtimes(cinema_hall_id: str) -> List[Showtime]:
    """Get all showtimes for a cinema hall."""
    try:
        today = date.today()
        return list(Showtime.objects.filter(
            cinema_hall_id=cinema_hall_id,
            starts_at__date=today
        ).select_related('movie').order_by('starts_at'))
    except Exception as e:
        print(f"Error in get_cinema_hall_showtimes: {str(e)}")
        return []

@sync_to_async
def get_cinema_hall_movies(cinema_hall_id: str) -> List[Movie]:
    """Get all movies showing at a cinema hall."""
    try:
        today = date.today()
        showtimes = Showtime.objects.filter(
            cinema_hall_id=cinema_hall_id,
            starts_at__date=today
        ).select_related('movie')
        
        # Get unique movies and their showtimes
        movies_with_times = {}
        for showtime in showtimes:
            if showtime.movie not in movies_with_times:
                movies_with_times[showtime.movie] = []
            movies_with_times[showtime.movie].append(showtime.starts_at.strftime("%I:%M %p"))
        
        return [(movie, times) for movie, times in movies_with_times.items()]
    except Exception as e:
        print(f"Error in get_cinema_hall_movies: {str(e)}")
        return []

@sync_to_async
def filter_movies_by_genre(genre: str) -> List[Movie]:
    """Get movies of a specific genre."""
    try:
        # Clean and standardize the genre name
        clean_genre = genre.strip().lower()
        
        # First try to find the genre
        genre_obj = Genre.objects.filter(type__icontains=clean_genre).first()
        if genre_obj:
            # Then get movies with that genre
            return list(Movie.objects.filter(genres=genre_obj).order_by('-imdb_rating')[:5])
        return []
    except Exception:
        return []

@sync_to_async
def filter_family_friendly_movies() -> List[Movie]:
    """Get family-friendly movies."""
    return list(Movie.objects.all()[:5])  # Since age_rating is not available, return all movies

@sync_to_async
def filter_current_movies() -> List[Movie]:
    """Get currently showing movies."""
    return list(Movie.objects.all()[:5])

@sync_to_async
def filter_upcoming_movies(today: date) -> List[Movie]:
    """Get upcoming movie releases."""
    return list(Movie.objects.filter(release_date__gt=today).order_by('release_date')[:5])

@sync_to_async
def filter_top_rated_movies() -> List[Movie]:
    """Get top-rated movies."""
    return list(Movie.objects.order_by("-imdb_rating")[:5])

@sync_to_async
def filter_kid_friendly_movies() -> List[Movie]:
    """Get movies suitable for kids."""
    return list(Movie.objects.all()[:5])

@sync_to_async
def filter_festival_movies() -> List[Movie]:
    """Get movies that were featured in festivals."""
    return list(Movie.objects.filter(festival__isnull=False)[:5])

# Base action class with common functionality
class BaseAction(Action, ABC):
    @abstractmethod
    def name(self) -> Text:
        """Return the name of the action."""
        pass

    async def handle_error(self, dispatcher: CollectingDispatcher, error: Exception) -> None:
        """Handle errors in a consistent way."""
        dispatcher.utter_message(text=GENERAL_ERROR.format(error=str(error)))

    def format_movie_list(self, movies: List[Movie], format_str: str = "{title}") -> str:
        """Format a list of movies into a readable string."""
        if not movies:
            return ""
        return ", ".join([format_str.format(title=m.title, rating=m.user_rating, date=m.release_date) for m in movies])

    async def handle_movie_not_found(self, dispatcher: CollectingDispatcher, movie_name: str) -> None:
        """Handle cases where a movie is not found in a consistent and helpful way."""
        # First, try to find similar movies
        try:
            similar_terms = movie_name.lower().split()
            query = Q()
            for term in similar_terms:
                if len(term) > 3:  # Only use terms longer than 3 characters
                    query |= Q(title__icontains=term)
            
            similar_movies = await sync_to_async(list)(Movie.objects.filter(query)[:5])
            
            message = [f"Sorry, I couldn't find '{movie_name}' in our database. This could be because:"]
            message.append("1. The movie hasn't been added to our system yet")
            message.append("2. There might be a typo in the movie name")
            message.append("3. The movie might be listed under a different title")
            
            if similar_movies:
                message.append("\nDid you mean one of these movies?")
                for movie in similar_movies:
                    message.append(f"- {movie.title}")
            
            message.append("\nPlease check the movie name and try again, or ask about a different movie.")
            dispatcher.utter_message(text="\n".join(message))
        except Exception as e:
            print(f"Error in handle_movie_not_found: {str(e)}")
            dispatcher.utter_message(text=f"Sorry, I couldn't find '{movie_name}' in our database.")

# Basic conversation actions
class ActionGreet(BaseAction):
    def name(self) -> Text:
        return "action_greet"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_greet")
        return []

class ActionGoodbye(BaseAction):
    def name(self) -> Text:
        return "action_goodbye"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_goodbye")
        return []
    
class ActionHelp(BaseAction):
    def name(self) -> Text:
        return "action_help"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_help")
        return []

class ActionBotChallenge(BaseAction):
    def name(self) -> Text:
        return "action_bot_challenge"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_iamabot")
        return []

class ActionAffirm(BaseAction):
    def name(self) -> Text:
        return "action_affirm"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_affirm")
        return []

class ActionDeny(BaseAction):
    def name(self) -> Text:
        return "action_deny"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_deny")
        return []

class ActionFallback(BaseAction):
    def name(self) -> Text:
        return "action_fallback"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_fallback")
        return []
    
class ActionAskMovieShowtimes(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_showtimes"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text=PROVIDE_MOVIE_NAME)
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if not movie:
                await self.handle_movie_not_found(dispatcher, movie_name)
                return []

            showtimes = await get_movie_showtimes(movie.id)
            if showtimes:
                showtime_text = "\n".join([
                    f"- {showtime.time} at {showtime.cinema_hall.name}"
                    for showtime in showtimes
                ])
                response = f"Showtimes for {movie.title}:\n{showtime_text}"
            else:
                response = f"No showtimes available for {movie.title}."
            
            dispatcher.utter_message(text=response)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieCast(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_cast"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                print(f"Debug - Movie found: {movie.title}")
                print(f"Debug - Movie actors: {movie.actors}")
                print(f"Debug - Has actors attribute: {hasattr(movie, 'actors')}")
                
                if hasattr(movie, 'actors') and movie.actors:
                    dispatcher.utter_message(text=f"The cast of {movie.title} includes: {movie.actors}")
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have cast information for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            print(f"Debug - Error in ActionAskMovieCast: {str(e)}")
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieDirector(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_director"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please provide the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                if hasattr(movie, 'director'):
                    # Convert to string if it's a list
                    director = movie.director[0] if isinstance(movie.director, list) else movie.director
                    dispatcher.utter_message(text=f"The director of {movie.title} is {director}.")
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have director information for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieRating(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_rating"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                if hasattr(movie, 'imdb_rating') and movie.imdb_rating:
                    dispatcher.utter_message(text=f"{movie.title} has an IMDb rating of {movie.imdb_rating}/10.")
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have rating information for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieGenre(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_genre"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                if hasattr(movie, 'genres') and movie.genres.exists():
                    genres = ", ".join([genre.type for genre in movie.genres.all()])
                    dispatcher.utter_message(text=f"{movie.title} belongs to the following genres: {genres}")
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have genre information for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieLocation(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_location"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify which movie you'd like to know about.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                cinema_halls = await get_movie_cinema_halls(movie.id)
                if cinema_halls:
                    locations = ", ".join(cinema_halls)
                    dispatcher.utter_message(text=f"{movie.title} is being screened at: {locations}")
                else:
                    dispatcher.utter_message(text=f"{movie.title} is not currently showing in any cinema halls.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskTicketValidity(BaseAction):
    def name(self) -> Text:
        return "action_ask_ticket_validity"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Tickets are valid only for the selected showtime and cannot be reused.")
        return []

class ActionAskMovieInfo(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_info"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify which movie you'd like to know about.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                info = []
                info.append(f"Title: {movie.title}")
                
                if hasattr(movie, 'genres') and movie.genres.exists():
                    genres = ", ".join([genre.type for genre in movie.genres.all()])
                    info.append(f"Genre: {genres}")
                
                if hasattr(movie, 'director') and movie.director:
                    director = movie.director[0] if isinstance(movie.director, list) else movie.director
                    info.append(f"Director: {director}")
                
                if hasattr(movie, 'release_date') and movie.release_date:
                    info.append(f"Release Date: {movie.release_date}")
                
                if hasattr(movie, 'imdb_rating') and movie.imdb_rating:
                    info.append(f"Rating: {movie.imdb_rating}/10")
                
                if hasattr(movie, 'description') and movie.description:
                    info.append(f"Description: {movie.description}")
                
                if info:
                    response = "\n".join(info)
                    dispatcher.utter_message(text=response)
                else:
                    dispatcher.utter_message(text=f"I found {movie.title}, but I don't have any additional information about it.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskReleaseDate(BaseAction):
    def name(self) -> Text:
        return "action_ask_release_date"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                if hasattr(movie, 'release_date') and movie.release_date:
                    dispatcher.utter_message(text=f"{movie.title} was released on {movie.release_date}.")
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have release date information for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskTicketPrice(BaseAction):
    def name(self) -> Text:
        return "action_ask_ticket_price"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="The standard ticket price is 100 EGP. Premium options may cost more depending on the cinema.")
        return []

class ActionAskMovieDuration(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_duration"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if movie_name:
            try:
                movie = await get_movie_by_name(movie_name)
                if movie:
                    dispatcher.utter_message(text=f"The duration of {movie.title} is {movie.duration} minutes.")
                else:
                    await self.handle_movie_not_found(dispatcher, movie_name)
            except Exception as e:
                dispatcher.utter_message(text=f"Sorry, an error occurred: {str(e)}")
        else:
            dispatcher.utter_message(text="Please specify the movie name.")
        return []

class ActionAskMovieAvailability(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_availability"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                if hasattr(movie, 'is_available'):
                    response = f"{movie.title} is currently {'available' if movie.is_available else 'not available'} in cinemas."
                else:
                    response = f"Sorry, I don't have availability information for {movie.title}."
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
            dispatcher.utter_message(text=response)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieLanguage(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_language"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if movie_name:
            try:
                movie = await get_movie_by_name(movie_name)
                if movie:
                    dispatcher.utter_message(text=f"{movie.title} is available in {movie.language}.")
                else:
                    await self.handle_movie_not_found(dispatcher, movie_name)
            except Exception as e:
                dispatcher.utter_message(text=f"Sorry, an error occurred: {str(e)}")
        else:
            dispatcher.utter_message(text="Please provide the movie name.")
        return []

class ActionAskMovieSubtitles(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_subtitles"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if movie_name:
            try:
                movie = await get_movie_by_name(movie_name)
                if movie:
                    if movie.subtitles:
                        dispatcher.utter_message(text=f"{movie.title} provides subtitles.")
                    else:
                        dispatcher.utter_message(text=f"{movie.title} does not provide subtitles.")
                else:
                    await self.handle_movie_not_found(dispatcher, movie_name)
            except Exception as e:
                dispatcher.utter_message(text=f"Sorry, an error occurred: {str(e)}")
        else:
            dispatcher.utter_message(text="Please provide the movie name.")
        return []

class ActionAskMovieSuitable(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_suitable"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if movie_name:
            try:
                movie = await get_movie_by_name(movie_name)
                if movie:
                    dispatcher.utter_message(text=f"{movie.title} is suitable for ages: {movie.age_rating}.")
                else:
                    await self.handle_movie_not_found(dispatcher, movie_name)
            except Exception as e:
                dispatcher.utter_message(text=f"Sorry, an error occurred: {str(e)}")
        else:
            dispatcher.utter_message(text="Please provide the movie name.")
        return []

class ActionAskGenreRecommendation(BaseAction):
    def name(self) -> Text:
        return "action_ask_genre_recommendation"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        genre = tracker.get_slot("genre")
        if not genre:
            dispatcher.utter_message(text="Which genre do you prefer?")
            return []

        try:
            movies = await filter_movies_by_genre(genre)
            if movies:
                titles = ", ".join([f"{m.title} ({m.imdb_rating}/10)" for m in movies])
                response = f"Here are some top-rated {genre} movies: {titles}"
            else:
                response = f"I couldn't find any movies in the {genre} genre."
            dispatcher.utter_message(text=response)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskFamilyFriendly(BaseAction):
    def name(self) -> Text:
        return "action_ask_family_friendly"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            movies = await filter_family_friendly_movies()
            if movies:
                titles = ", ".join([m.title for m in movies])
                response = f"These are family-friendly movies: {titles}."
            else:
                response = "I couldn't find family-friendly movies right now."
        except Exception as e:
            response = f"Sorry, an error occurred: {str(e)}"

        dispatcher.utter_message(text=response)
        return []

class ActionAskMovieTheaterAvailability(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_theater_availability"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                cinema_halls = await get_movie_cinema_halls(movie.id)
                if cinema_halls:
                    response = f"{movie.title} is being shown at: {', '.join(cinema_halls)}"
                else:
                    response = f"{movie.title} is not currently in theaters."
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
            dispatcher.utter_message(text=response)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskUserRating(BaseAction):
    def name(self) -> Text:
        return "action_ask_user_rating"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Which movie are you asking about?")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                response = f"The user rating for {movie.title} is {movie.imdb_rating}/10."
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            response = f"Sorry, an error occurred: {str(e)}"

        dispatcher.utter_message(text=response)
        return []

class ActionAskCurrentMovies(BaseAction):
    def name(self) -> Text:
        return "action_ask_current_movies"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            movies = await filter_current_movies()
            if movies:
                titles = ", ".join([m.title for m in movies])
                response = f"Currently showing movies: {titles}."
            else:
                response = "There are no movies showing at the moment."
        except Exception as e:
            response = f"Sorry, an error occurred: {str(e)}"

        dispatcher.utter_message(text=response)
        return []

class ActionAskUpcomingReleases(BaseAction):
    def name(self) -> Text:
        return "action_ask_upcoming_releases"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        today = date.today()
        try:
            upcoming = await filter_upcoming_movies(today)
            if upcoming:
                titles = ", ".join([f"{m.title} ({m.release_date})" for m in upcoming])
                response = f"Upcoming releases: {titles}."
            else:
                response = "No upcoming releases found."
        except Exception as e:
            response = f"Sorry, an error occurred: {str(e)}"

        dispatcher.utter_message(text=response)
        return []

class ActionAskTopRatedMovies(BaseAction):
    def name(self) -> Text:
        return "action_ask_top_rated_movies"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            movies = await filter_top_rated_movies()
            if movies:
                titles = ", ".join([f"{m.title} ({m.imdb_rating}/10)" for m in movies])
                response = f"Here are the top-rated movies: {titles}"
            else:
                response = "No top-rated movies found."
            dispatcher.utter_message(text=response)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieFestivals(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_festivals"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            movies = await filter_festival_movies()
            if movies:
                info = ", ".join([f"{m.title} ({m.festival})" for m in movies if m.festival])
                response = f"These movies were featured in festivals: {info}."
            else:
                response = "No festival movies found."
        except Exception as e:
            response = f"Sorry, an error occurred: {str(e)}"

        dispatcher.utter_message(text=response)
        return []

class ActionAskMovieDescription(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_description"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please provide the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie and movie.description:
                dispatcher.utter_message(text=f"Here's what {movie.title} is about: {movie.description}")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskKidFriendlyMovies(BaseAction):
    def name(self) -> Text:
        return "action_ask_kid_friendly_movies"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            movies = await filter_kid_friendly_movies()
            if movies:
                titles = ", ".join([m.title for m in movies])
                response = f"These are kid-friendly movies: {titles}."
            else:
                response = "No kid-friendly movies available right now."
        except Exception as e:
            response = f"Sorry, an error occurred: {str(e)}"

        dispatcher.utter_message(text=response)
        return []

class ActionAskStreamingPlatform(BaseAction):
    def name(self) -> Text:
        return "action_ask_streaming_platform"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please provide the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                response = f"{movie.title} is available on: {movie.streaming_platform}" if movie.streaming_platform else "This movie is not available on any streaming platform."
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            response = f"Sorry, an error occurred: {str(e)}"

        dispatcher.utter_message(text=response)
        return []

class ActionAsk3DAvailability(BaseAction):
    def name(self) -> Text:
        return "action_ask_3d_availability"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please provide the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                response = f"{movie.title} {'supports' if movie.is_3d else 'does not support'} 3D viewing."
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            response = f"Sorry, an error occurred: {str(e)}"

        dispatcher.utter_message(text=response)
        return []

class ActionAskMoviePoster(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_poster"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Get all slots that might contain the movie name
        movie_name = next((
            value for slot, value in tracker.slots.items()
            if slot in ["movie_name", "movie"] and value is not None
        ), None)

        if not movie_name:
            dispatcher.utter_message(text="Which movie's poster would you like to see?")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                if hasattr(movie, 'poster') and movie.poster:
                    dispatcher.utter_message(
                        text=f"Here's the poster for {movie.title}:",
                        image=movie.poster
                    )
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have a poster for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieTrailer(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_trailer"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                if hasattr(movie, 'trailer_url') and movie.trailer_url:
                    dispatcher.utter_message(text=f"Here's the trailer for {movie.title}: {movie.trailer_url}")
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have a trailer link for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMovieSeats(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_seats"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please provide the movie name.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                seats = await get_movie_seats(movie.id)
                if seats is not None:
                    dispatcher.utter_message(text=f"{movie.title} has {seats} seats available.")
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have seat information for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskMoviePrice(BaseAction):
    def name(self) -> Text:
        return "action_ask_movie_price"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        movie_name = tracker.get_slot("movie_name")
        if not movie_name:
            dispatcher.utter_message(text="Please specify which movie you'd like to know the price for.")
            return []

        try:
            movie = await get_movie_by_name(movie_name)
            if movie:
                if hasattr(movie, 'ticket_price') and movie.ticket_price:
                    dispatcher.utter_message(text=f"The ticket price for {movie.title} is ${movie.ticket_price:.2f}.")
                else:
                    dispatcher.utter_message(text=f"Sorry, I don't have ticket price information for {movie.title}.")
            else:
                await self.handle_movie_not_found(dispatcher, movie_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskCinemaHallInfo(BaseAction):
    def name(self) -> Text:
        return "action_ask_cinema_hall_info"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        cinema_hall_name = tracker.get_slot("cinema_hall")
        if not cinema_hall_name:
            dispatcher.utter_message(text="Please specify which cinema you'd like to know about.")
            return []

        try:
            cinema = await get_cinema_hall_by_name(cinema_hall_name)
            if cinema:
                info = []
                info.append(f"Name: {cinema.name}")
                
                if hasattr(cinema, 'location') and cinema.location:
                    info.append(f"Location: {cinema.location}")
                
                if hasattr(cinema, 'total_seats') and cinema.total_seats:
                    info.append(f"Total Seats: {cinema.total_seats}")
                
                if hasattr(cinema, 'number_of_screens') and cinema.number_of_screens:
                    info.append(f"Number of Screens: {cinema.number_of_screens}")
                
                if hasattr(cinema, 'facilities') and cinema.facilities:
                    info.append(f"Facilities: {cinema.facilities}")
                
                if info:
                    response = "\n".join(info)
                    dispatcher.utter_message(text=response)
                else:
                    dispatcher.utter_message(text=f"I found {cinema.name}, but I don't have any additional information about it.")
            else:
                await self.handle_movie_not_found(dispatcher, cinema_hall_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskCinemaHallMovies(BaseAction):
    def name(self) -> Text:
        return "action_ask_cinema_hall_movies"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        cinema_hall_name = tracker.get_slot("cinema_hall")
        if not cinema_hall_name:
            dispatcher.utter_message(text="Please specify which cinema you'd like to know about.")
            return []

        try:
            cinema = await get_cinema_hall_by_name(cinema_hall_name)
            if cinema:
                movies = await get_cinema_hall_movies(cinema.id)
                if movies:
                    response = [f"Today's movies at {cinema.name}:"]
                    for movie, showtimes in movies:
                        movie_info = f"\n• {movie.title}"
                        if hasattr(movie, 'imdb_rating') and movie.imdb_rating:
                            movie_info += f" ({movie.imdb_rating}/10)"
                        movie_info += f"\n  Showtimes: {', '.join(showtimes)}"
                        response.append(movie_info)
                    
                    dispatcher.utter_message(text="\n".join(response))
                else:
                    dispatcher.utter_message(text=f"No movies are scheduled at {cinema.name} for today.")
            else:
                await self.handle_movie_not_found(dispatcher, cinema_hall_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskCinemaHallFacilities(BaseAction):
    def name(self) -> Text:
        return "action_ask_cinema_hall_facilities"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        cinema_hall_name = tracker.get_slot("cinema_hall")
        if not cinema_hall_name:
            dispatcher.utter_message(text="Please specify which cinema you'd like to know about.")
            return []

        try:
            cinema = await get_cinema_hall_by_name(cinema_hall_name)
            if cinema:
                facilities = []
                
                if hasattr(cinema, 'facilities') and cinema.facilities:
                    facilities.append(cinema.facilities)
                
                if hasattr(cinema, 'has_parking') and cinema.has_parking:
                    facilities.append("Parking available")
                
                if hasattr(cinema, 'has_food') and cinema.has_food:
                    facilities.append("Food and beverages")
                
                if hasattr(cinema, 'has_vip') and cinema.has_vip:
                    facilities.append("VIP section")
                
                if facilities:
                    response = f"Facilities at {cinema.name}:\n- " + "\n- ".join(facilities)
                    dispatcher.utter_message(text=response)
                else:
                    dispatcher.utter_message(text=f"I don't have information about facilities at {cinema.name}.")
            else:
                await self.handle_movie_not_found(dispatcher, cinema_hall_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []

class ActionAskCinemaSchedule(BaseAction):
    def name(self) -> Text:
        return "action_ask_cinema_schedule"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        cinema_hall_name = tracker.get_slot("cinema_hall")
        if not cinema_hall_name:
            dispatcher.utter_message(text="Please specify which cinema you'd like to know about.")
            return []

        try:
            cinema = await get_cinema_hall_by_name(cinema_hall_name)
            if cinema:
                showtimes = await get_cinema_hall_showtimes(cinema.id)
                if showtimes:
                    response = [f"Today's schedule at {cinema.name}:"]
                    current_movie = None
                    movie_times = []
                    
                    for showtime in showtimes:
                        if current_movie != showtime.movie:
                            # Add previous movie's info if exists
                            if current_movie and movie_times:
                                movie_info = f"\n• {current_movie.title}"
                                if hasattr(current_movie, 'imdb_rating') and current_movie.imdb_rating:
                                    movie_info += f" ({current_movie.imdb_rating}/10)"
                                movie_info += f"\n  Showtimes: {', '.join(movie_times)}"
                                response.append(movie_info)
                            
                            # Start new movie
                            current_movie = showtime.movie
                            movie_times = []
                        
                        movie_times.append(showtime.starts_at.strftime("%I:%M %p"))
                    
                    # Add the last movie's info
                    if current_movie and movie_times:
                        movie_info = f"\n• {current_movie.title}"
                        if hasattr(current_movie, 'imdb_rating') and current_movie.imdb_rating:
                            movie_info += f" ({current_movie.imdb_rating}/10)"
                        movie_info += f"\n  Showtimes: {', '.join(movie_times)}"
                        response.append(movie_info)
                    
                    # Add available seats info if exists
                    for showtime in showtimes:
                        if hasattr(showtime, 'available_seats') and showtime.available_seats is not None:
                            time_str = showtime.starts_at.strftime("%I:%M %p")
                            response.append(f"\nAvailable seats for {showtime.movie.title} at {time_str}: {showtime.available_seats}")
                    
                    dispatcher.utter_message(text="\n".join(response))
                else:
                    dispatcher.utter_message(text=f"No shows are scheduled at {cinema.name} for today.")
            else:
                await self.handle_movie_not_found(dispatcher, cinema_hall_name)
        except Exception as e:
            await self.handle_error(dispatcher, e)
        return []